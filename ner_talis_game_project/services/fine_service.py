"""Raid, city fine and movement restriction runtime for illegal Seldar activities."""

from __future__ import annotations

import math
import logging
import random
import time
import uuid
from dataclasses import dataclass
from typing import Any

from services.derived_stats_service import safe_int
logger=logging.getLogger(__name__)

RAID_CHANCE_PERCENT = 15
BASE_FINE_COPPER = 100
SECONDS_PER_FINE_DAY = 24 * 60 * 60
DAILY_INTEREST_PERCENT = 1

FINE_STATUS_VOLUNTARY = "voluntary"
FINE_STATUS_OVERDUE = "overdue"
FINE_STATUS_FORCED = "forced_collection"
FINE_STATUS_PAID = "paid"
FINE_STATUS_REMOVED = "removed_by_admin"
FINE_STATUS_EXPIRED = "expired"
FINE_STATUS_CANCELLED = "cancelled"

# Терминальные статусы: штраф с любым из них больше НЕ активен (не отображается,
# не ограничивает, не начисляет проценты). Раньше активность проверялась только
# как «status != paid», поэтому штраф с любым иным терминальным/повреждённым
# статусом «висел» навсегда — это и есть корень бага неснимаемого штрафа (ТЗ §1).
INACTIVE_FINE_STATUSES = frozenset({
    FINE_STATUS_PAID, FINE_STATUS_REMOVED, FINE_STATUS_EXPIRED, FINE_STATUS_CANCELLED,
})


def is_fine_active(fine: Any) -> bool:
    """Штраф активен, если это словарь и его статус не терминальный.

    Неизвестный/пустой статус трактуем как активный (безопасно: лучше показать
    штраф и дать его снять, чем тихо скрыть)."""
    if not isinstance(fine, dict):
        return False
    return str(fine.get("status") or FINE_STATUS_VOLUNTARY) not in INACTIVE_FINE_STATUSES

CITY_FINE_SOURCE_LABELS = {
    "black_market": "Чёрный рынок",
    "informer_krot": "Информатор Крот",
    "underground_casino": "Подпольное казино",
}
SOURCE_ALIASES = {
    "black_market":"black_market","black_market_raid":"black_market","seldar_black_market":"black_market","seldar_npc_market_black":"black_market","seldar_npc_market_black_buy":"black_market","seldar_npc_market_black_sell":"black_market","чёрный рынок":"black_market","черный рынок":"black_market",
    "informer_krot":"informer_krot","informer_raid":"informer_krot","krot":"informer_krot","mole":"informer_krot","seldar_informer_mole":"informer_krot","информатор крот":"informer_krot","крот":"informer_krot",
    "underground_casino":"underground_casino","casino":"underground_casino","casino_raid":"underground_casino","seldar_underground_casino":"underground_casino","подпольное казино":"underground_casino",
}
SOURCE_NAMES={"black_market":"Чёрный рынок","informer_krot":"Информатор Крот","underground_casino":"Подпольное казино","unknown":"Неизвестный источник"}

def normalize_fine_source(source: str|None, source_name: str|None=None) -> str:
    for value in (source,source_name):
        key=str(value or "").strip().casefold()
        if key in SOURCE_ALIASES:return SOURCE_ALIASES[key]
    return str(source or "unknown").strip() or "unknown"

def _history(player:dict[str,Any],action:str,fine:dict[str,Any]|None=None,**extra:Any)->None:
    fine=fine or {};player.setdefault("fine_history",[]).append({"action":action,"fine_id":fine.get("id"),"source":fine.get("source"),"source_name":fine.get("source_name"),"amount":safe_int(fine.get("current_amount"),0),"created_at_ts":_now_ts(),**extra});logger.debug("%s game_id=%s fine_id=%s source=%s",action,player.get("game_id"),fine.get("id"),fine.get("source"))
def _fine_text(fine:dict[str,Any],key:str,default:str,**values:Any)->str:
    template=str((fine.get("messages") or {}).get(key) or default);values={"fine_id":fine.get("id"),"source":fine.get("source_name"),"amount":fine.get("current_amount"),"day":fine.get("current_day"),**values}
    try:return template.format_map(values)
    except (KeyError,ValueError):return template

RAID_ACTION_SOURCES = {
    "Чёрный рынок": "black_market",
    "Информатор Крот": "informer_krot",
    "Подпольное казино": "underground_casino",
}

RAID_ZONE_SOURCES = {
    "seldar_black_market": "black_market",
    "seldar_informer_mole": "informer_krot",
    "seldar_underground_casino": "underground_casino",
}

CITY_ZONE_PREFIXES = ("seldar_",)
STARTING_LOCATION_IDS = {"hilly_meadows", "ordinary_forest"}
STARTING_ZONE_PREFIXES = ("hilly_meadows", "ordinary_forest")
RESTRICTED_CITY_ACTIONS = {
    "В город",
    "Центральная площадь",
    "⬅️ Центральная площадь",
    "Вернуться в город",
    "Вернуться к воротам Селдара",
    "Вернуться к воротам",
}
RESTRICTED_STARTING_ACTIONS = {"Холмистые луга", "Обыкновенный лес"}

CITY_FINE_PAY_ACTION = "Оплатить штраф"
CITY_HALL_BACK = "Назад в Ратушу"
FORTRESS_HALL = "Крепостная Ратуша"
FORTRESS_BACK = "Назад в Крепостную Ратушу"
STAY_IN_FORTRESS = "Остаться в Крепости"
MAINLAND_EXTERNAL = "Внешние локации материка"


@dataclass(frozen=True)
class FineActionResult:
    text: str
    buttons: list[list[str]]
    zone_id: str
    extra_messages: tuple[str, ...] = ()


@dataclass(frozen=True)
class FineAdvanceResult:
    messages: tuple[str, ...] = ()
    moved_to_fortress: bool = False
    changed: bool = False


def _central_square_buttons() -> list[list[str]]:
    """Full Central Square keypad after a raid relocation.

    Lazy import avoids the circular dependency (city_service imports this module),
    so a raid drop-off shows every quarter/gate button, not just three quarters.
    """
    try:
        from services.city_service import central_square_buttons

        return central_square_buttons()
    except Exception:
        return [["Портовый квартал", "Торговый квартал"], ["Ремесленный квартал", "Верхний квартал"], ["Городские ворота", "Объявления"]]


def _now_ts(now: float | int | None = None) -> int:
    return int(time.time() if now is None else now)


def _money(player: dict[str, Any]) -> int:
    return max(0, safe_int(player.get("money_copper", player.get("money", 0)), 0))


def _set_money(player: dict[str, Any], value: int) -> None:
    value = max(0, safe_int(value, 0))
    player["money_copper"] = value
    player["money"] = value


def _fine(player: dict[str, Any]) -> dict[str, Any] | None:
    fine = player.get("active_fine")
    if isinstance(fine, dict) and fine.get("status") != FINE_STATUS_PAID:
        return fine
    return None


def has_active_fine(player: dict[str, Any]) -> bool:
    return _fine(player) is not None


def fine_source_label(source: str | None) -> str:
    return CITY_FINE_SOURCE_LABELS.get(str(source or ""), "Сомнительное место")


def calculate_level_bonus_percent(player_level: int) -> int:
    return max(0, math.floor(math.sqrt(max(1, safe_int(player_level, 1)))))


def _published_fine_definition(source: str | None) -> dict[str, Any]:
    aliases = {
        "black_market": "black_market_raid", "informer_krot": "informer_raid",
        "underground_casino": "casino_raid",
    }
    wanted = {str(source or ""), aliases.get(str(source or ""), "")}
    try:
        from services import fine_constructor_service as definitions
        rows = definitions.store().list(status=definitions.STATUS_PUBLISHED)
        matches = [row for row in rows if str((row.get("data") or {}).get("source") or "") in wanted]
        if not matches:
            matches = [row for row in rows if (row.get("data") or {}).get("type") in ("raid", "city")]
        return dict((matches[0].get("data") or {})) if matches else {}
    except Exception:
        return {}


def calculate_fine_amount(player: dict[str, Any], source: str | None = None) -> int:
    level_bonus_percent = calculate_level_bonus_percent(safe_int(player.get("level"), 1))
    definition = _published_fine_definition(source)
    base = max(0, safe_int(definition.get("base_amount"), BASE_FINE_COPPER))
    fallback = math.floor(base * (1 + level_bonus_percent / 100))
    try:
        from services.formula_runtime import evaluate, numeric_context
        value = evaluate(definition.get("amount_formula_id"), numeric_context({
            "base_amount": base, "bonus": level_bonus_percent,
            "multiplier": 1 + level_bonus_percent / 100,
        }, player=player), default=fallback)
        result = max(0, safe_int(value, fallback))
    except Exception:
        result = fallback
    minimum = safe_int(definition.get("min_amount"), 0)
    maximum = safe_int(definition.get("max_amount"), 0)
    if minimum > 0:
        result = max(minimum, result)
    if maximum > 0:
        result = min(maximum, result)
    return result


def current_fine_day(fine: dict[str, Any], now: float | int | None = None) -> int:
    created_at = safe_int(fine.get("created_at_ts"), 0)
    if created_at <= 0:
        created_at = _now_ts(now)
        fine["created_at_ts"] = created_at
    return max(1, 1 + ((_now_ts(now) - created_at) // SECONDS_PER_FINE_DAY))


def fine_status_for_day(day: int) -> str:
    if day >= 24:
        return FINE_STATUS_FORCED
    if day >= 8:
        return FINE_STATUS_OVERDUE
    return FINE_STATUS_VOLUNTARY


def _format_raid_text(fine_amount: int) -> str:
    return (
        "Пока вы занимались делами в тёмных переулках, шум вокруг резко изменился.\n"
        "Где-то рядом лязгнули доспехи, кто-то коротко свистнул, и из переулка вышли стражники города.\n\n"
        "— Стоять. По распоряжению городской стражи район закрыт на проверку.\n\n"
        "Вас выводят из тёмных переулков и сопровождают на Центральную площадь. "
        "За участие в сомнительных делах на вас наложен городской штраф.\n\n"
        f"Штраф: {fine_amount} медных монет.\n"
        "Срок добровольной оплаты: 7 дней.\n\n"
        "Оплатить штраф можно в Верхнем квартале, в Ратуше, у Управляющего."
    )


def create_raid_fine(player: dict[str, Any], source: str, now: float | int | None = None) -> dict[str, Any]:
    created_at = _now_ts(now)
    base_amount = calculate_fine_amount(player, source)
    fine = {
        "id": f"fine_{source}_{uuid.uuid4().hex[:12]}",
        "source": source,
        "source_name": fine_source_label(source),
        "created_at_ts": created_at,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(created_at)),
        "start_day": 1,
        "current_day": 1,
        "base_amount": base_amount,
        "current_amount": base_amount,
        "currency": "copper",
        "status": FINE_STATUS_VOLUNTARY,
        "last_interest_applied_day": 7,
        "first_deadline_day": 7,
        "second_start_day": 8,
        "second_deadline_day": 23,
        "third_start_day": 24,
        "movement_restricted": False,
        "can_pay_in_city_hall": True,
        "can_pay_in_fortress_hall": False,
        "paid_at": None,
        "notified_stages": [],
        "level_bonus_percent": calculate_level_bonus_percent(safe_int(player.get("level"), 1)),
    }
    player["active_fine"] = fine
    return fine


def move_player_to_central_square(player: dict[str, Any]) -> None:
    player["current_city"] = "seldar"
    player["current_zone"] = "seldar_central_square"
    player["location_id"] = "seldar_central_square"
    player["current_location"] = None
    player.pop("market_context", None)
    player.pop("crafting_context", None)
    player.pop("active_event", None)
    player.pop("active_timer", None)
    player["in_battle"] = False


def move_player_to_fortress(player: dict[str, Any]) -> None:
    player["current_city"] = "outside_seldar"
    player["current_zone"] = "fortress_in_gorge_courtyard"
    player["location_id"] = "fortress_in_gorge_courtyard"
    player["current_location"] = "fortress_in_gorge"
    player.pop("market_context", None)
    player.pop("crafting_context", None)
    player.pop("active_event", None)
    player.pop("active_timer", None)
    player["in_battle"] = False


def source_for_raid_action(player: dict[str, Any], action: str) -> str | None:
    action = str(action or "").strip()
    if action in RAID_ACTION_SOURCES:
        return RAID_ACTION_SOURCES[action]
    zone = str(player.get("current_zone") or player.get("location_id") or "")
    if zone in RAID_ZONE_SOURCES and action not in {"Портовый квартал", "⬅️ Центральная площадь", "Центральная площадь"}:
        return RAID_ZONE_SOURCES[zone]
    return None


def should_trigger_raid(rng: random.Random | Any | None = None) -> bool:
    rng = rng or random
    if hasattr(rng, "randint"):
        return rng.randint(1, 100) <= RAID_CHANCE_PERCENT
    return random.randint(1, 100) <= RAID_CHANCE_PERCENT


def maybe_trigger_raid(
    player: dict[str, Any],
    action: str,
    rng: random.Random | Any | None = None,
    now: float | int | None = None,
) -> FineActionResult | None:
    source = source_for_raid_action(player, action)
    if not source:
        return None
    if not should_trigger_raid(rng):
        return None

    existing = _fine(player)
    if existing is not None:
        advance_fine_state(player, now=now)
        move_player_to_central_square(player)
        amount = safe_int(existing.get("current_amount"), 0)
        return FineActionResult(
            text=(
                "Облава стражников! Вы перенесены на Центральную площадь.\n\n"
                f"У вас уже есть активный городской штраф: {amount} медных монет. "
                "Оплатите его у Управляющего."
            ),
            buttons=_central_square_buttons(),
            zone_id="seldar_central_square",
        )

    fine = create_raid_fine(player, source, now=now)
    move_player_to_central_square(player)
    amount = safe_int(fine.get("current_amount"), BASE_FINE_COPPER)
    return FineActionResult(
        text=_format_raid_text(amount),
        buttons=_central_square_buttons(),
        zone_id="seldar_central_square",
    )


def _apply_interest_until(fine: dict[str, Any], current_day: int) -> bool:
    start=max(1,safe_int(fine.get("interest_start_day"),safe_int(fine.get("overdue_day"),8)));last_day = safe_int(fine.get("last_interest_applied_day"), start-1)
    if current_day < start:
        fine["last_interest_applied_day"] = max(last_day, start-1)
        return False
    pct=max(0,float(fine.get("daily_interest_percent") or 0))
    if not fine.get("interest_enabled",True) or pct<=0:return False
    changed = False
    for _day in range(max(start, last_day + 1), current_day + 1):
        amount = max(0, safe_int(fine.get("current_amount"), 0))
        fine["current_amount"] = math.floor(amount * (1+pct/100))
        changed = True
    fine["last_interest_applied_day"] = max(last_day, current_day)
    return changed


def _is_city_or_starting_location(player: dict[str, Any]) -> bool:
    zone = str(player.get("current_zone") or player.get("location_id") or "")
    current_location = str(player.get("current_location") or "")
    if zone.startswith(CITY_ZONE_PREFIXES):
        return True
    if current_location in STARTING_LOCATION_IDS:
        return True
    return zone.startswith(STARTING_ZONE_PREFIXES)


def _notice_once(fine: dict[str, Any], key: str, text: str) -> str | None:
    notified = fine.setdefault("notified_stages", [])
    if not isinstance(notified, list):
        notified = []
        fine["notified_stages"] = notified
    if key in notified:
        return None
    notified.append(key)
    return text


def _first_deadline_letter(amount: int) -> str:
    return (
        "Эй, постой. У меня письмо для тебя. От городского Управляющего.\n\n"
        "Уведомление о просроченном штрафе\n\n"
        "Срок добровольной оплаты вашего штрафа истёк. С 8-го дня начинается второй срок взыскания. "
        "Он длится до конца 23-го дня. Каждый день к текущей сумме штрафа будет прибавляться 1%.\n\n"
        f"Текущая сумма штрафа: {amount} медных монет.\n\n"
        "Оплатить штраф всё ещё можно в Верхнем квартале, в Ратуше, у Управляющего."
    )


def _second_deadline_letter(amount: int) -> str:
    return (
        "Эй, тебя искали. Вот письмо. Сказали передать лично в руки.\n\n"
        "Последнее предупреждение о штрафе\n\n"
        "Второй срок взыскания истёк. С 24-го дня штраф переходит в бессрочное принудительное взыскание. "
        "Проценты продолжат начисляться ежедневно — 1% от текущей общей суммы штрафа — до полной оплаты.\n\n"
        f"Текущая сумма штрафа: {amount} медных монет."
    )


def _third_start_letter(amount: int) -> str:
    return (
        "Эй, стой. Для тебя письмо. На нём печать городской стражи.\n\n"
        "Постановление о принудительном ограничении передвижения\n\n"
        "Ваш штраф не был оплачен в установленный срок. Долг переведён в бессрочное взыскание. "
        "Каждый день к текущей сумме штрафа будет прибавляться 1% до полного погашения.\n\n"
        f"Текущая сумма штрафа: {amount} медных монет.\n\n"
        "С этого момента вам запрещён свободный проход в город и стартовые локации. "
        "Оплатить штраф теперь можно только в Крепостной Ратуше, у местного Управляющего."
    )


def _forced_move_text() -> str:
    return (
        "Стражники находят вас почти сразу после получения письма.\n\n"
        "— Приказ вступил в силу. До оплаты штрафа город и ближайшие земли для тебя закрыты.\n\n"
        "Вас сопровождают под надзором и отправляют в Крепость в ущелье."
    )


def advance_fine_state(player: dict[str, Any], now: float | int | None = None) -> FineAdvanceResult:
    fine = _fine(player)
    if fine is None:
        return FineAdvanceResult()

    changed = False
    messages: list[str] = []
    day = current_fine_day(fine, now=now)
    if safe_int(fine.get("current_day"), 1) != day:
        fine["current_day"] = day
        changed = True

    if _apply_interest_until(fine, day):
        changed = True

    status = fine_status_for_day(day)
    if fine.get("status") != status:
        fine["status"] = status
        changed = True
    fine["movement_restricted"] = status == FINE_STATUS_FORCED
    fine["can_pay_in_city_hall"] = status in {FINE_STATUS_VOLUNTARY, FINE_STATUS_OVERDUE}
    fine["can_pay_in_fortress_hall"] = status == FINE_STATUS_FORCED

    amount = max(0, safe_int(fine.get("current_amount"), 0))
    if day >= 8:
        text = _notice_once(fine, "first_deadline", _first_deadline_letter(amount))
        if text:
            messages.append(text)
            changed = True
    if day >= 24:
        text = _notice_once(fine, "second_deadline", _second_deadline_letter(amount))
        if text:
            messages.append(text)
            changed = True
        text = _notice_once(fine, "third_start", _third_start_letter(amount))
        if text:
            messages.append(text)
            changed = True

    moved = False
    if status == FINE_STATUS_FORCED and _is_city_or_starting_location(player):
        move_player_to_fortress(player)
        messages.append(_forced_move_text())
        moved = True
        changed = True

    return FineAdvanceResult(messages=tuple(messages), moved_to_fortress=moved, changed=changed)


def is_forced_collection(player: dict[str, Any]) -> bool:
    fine = _fine(player)
    return bool(fine and fine.get("status") == FINE_STATUS_FORCED)


def movement_block_buttons() -> list[list[str]]:
    return [[FORTRESS_HALL], [STAY_IN_FORTRESS], [MAINLAND_EXTERNAL]]


def movement_block_text() -> str:
    return (
        "У ворот вас останавливает крепостной стражник.\n\n"
        "— Дальше нельзя. В городской книге ты числишься должником. Пока штраф не оплачен, "
        "путь в город и стартовые земли закрыт.\n\n"
        "Стражник указывает в сторону Крепостной Ратуши.\n\n"
        "— Хочешь снять запрет — иди к Управляющему и погаси долг."
    )


def should_block_movement_action(player: dict[str, Any], action: str) -> bool:
    if not is_forced_collection(player):
        return False
    action = str(action or "").strip()
    if action in RESTRICTED_CITY_ACTIONS or action in RESTRICTED_STARTING_ACTIONS:
        return True
    return False


def fine_status_label(status: str) -> str:
    return {
        FINE_STATUS_VOLUNTARY: "Добровольная оплата",
        FINE_STATUS_OVERDUE: "Просрочка",
        FINE_STATUS_FORCED: "Принудительное взыскание",
        FINE_STATUS_PAID: "Оплачен",
    }.get(status, status)


def fine_card(player: dict[str, Any], *, place: str = "city", now: float | int | None = None) -> FineActionResult:
    advance_fine_state(player, now=now)
    fine = _fine(player)
    zone_id = "seldar_town_hall" if place == "city" else "fortress_in_gorge_fortress_hall"
    buttons = [[CITY_FINE_PAY_ACTION], [CITY_HALL_BACK if place == "city" else FORTRESS_BACK]]
    if fine is None:
        return FineActionResult("В городской книге долгов на ваше имя нет активных штрафов.", buttons[1:], zone_id)
    day = current_fine_day(fine, now=now)
    status = str(fine.get("status") or FINE_STATUS_VOLUNTARY)
    if status == FINE_STATUS_VOLUNTARY:
        next_stage = "Просрочка"
        days_left = max(0, 8 - day)
        interest_info = "нет"
    elif status == FINE_STATUS_OVERDUE:
        next_stage = "Принудительное взыскание"
        days_left = max(0, 24 - day)
        interest_info = "+1% ежедневно"
    else:
        next_stage = "нет, штраф бессрочный до оплаты"
        days_left = 0
        interest_info = "+1% ежедневно"
    text = (
        "Городской штраф\n\n"
        f"Сумма: {safe_int(fine.get('current_amount'), 0)} медных монет\n"
        f"Статус: {fine_status_label(status)}\n"
        f"Текущий день штрафа: {day}\n"
        f"Следующий этап: {next_stage}\n"
        f"До следующего этапа: {days_left} дн.\n"
        f"Ежедневные проценты: {interest_info}\n\n"
        "Оплатить штраф?"
    )
    return FineActionResult(text, buttons, zone_id)


# --- Multi-fine v2 helpers -------------------------------------------------
# Re-defined near the end intentionally: legacy save files used ``active_fine``;
# new logic stores all active fines in ``active_fines`` and keeps active_fine as
# a compatibility alias for the first unpaid fine.

def active_fines(player: dict[str, Any]) -> list[dict[str, Any]]:
    fines: list[dict[str, Any]] = []
    raw = player.get("active_fines")
    if isinstance(raw, list):
        for fine in raw:
            if is_fine_active(fine):
                fines.append(fine)
    legacy = player.get("active_fine")
    if is_fine_active(legacy):
        legacy_id = str(legacy.get("id") or "")
        if not legacy_id or all(str(f.get("id") or "") != legacy_id for f in fines):
            fines.append(legacy)
    player["active_fines"] = fines
    _sync_active_fine_alias(player)
    return fines


def _sync_active_fine_alias(player: dict[str, Any]) -> None:
    fines = [fine for fine in player.get("active_fines", []) if is_fine_active(fine)]
    player["active_fines"] = fines
    if fines:
        player["active_fine"] = fines[0]
    else:
        player.pop("active_fine", None)


def _fine(player: dict[str, Any]) -> dict[str, Any] | None:  # type: ignore[override]
    fines = active_fines(player)
    return fines[0] if fines else None


def has_active_fine(player: dict[str, Any]) -> bool:  # type: ignore[override]
    return bool(active_fines(player))

def fine_restrictions(player:dict[str,Any])->set[str]:
    result:set[str]=set()
    for fine in active_fines(player):
        for row in fine.get("restrictions") or []:result.add(str(row.get("code") if isinstance(row,dict) else row))
        if fine.get("status")==FINE_STATUS_FORCED:result.update({"block_city","block_starting","force_fortress"})
    return result

def fine_action_block_text(player:dict[str,Any],action:str)->str|None:
    restrictions=fine_restrictions(player);low=str(action or "").casefold();code=None
    checks=(("block_black_market",("чёрн","black_market")),("block_casino",("казино","casino")),("block_market",("рынок","market","магазин")),("block_delivery",("достав","delivery")),("block_craft",("ремес","крафт","craft","кузн")),("block_trade",("торгов","продать","купить")),("block_npc",("npc:","нпс:")),("block_event",("событ","эвент","event")),("block_quests",("квест","задани","quest")),("block_raids",("рейд","raid")),("block_transfer",("передач","transfer")))
    for candidate,needles in checks:
        if candidate in restrictions and any(needle in low for needle in needles):code=candidate;break
    if not code:return None
    fine=next((row for row in active_fines(player) if code in {str(x.get("code") if isinstance(x,dict) else x) for x in row.get("restrictions") or []}),active_fines(player)[0] if active_fines(player) else {})
    return _fine_text(fine,"on_block","Это действие недоступно из-за активного штрафа.",action=action,restriction=code)


def create_raid_fine(player: dict[str, Any], source: str, now: float | int | None = None) -> dict[str, Any]:  # type: ignore[override]
    created_at = _now_ts(now)
    source=normalize_fine_source(source)
    definition=_published_fine_definition(source);base_amount = calculate_fine_amount(player, source);overdue=max(2,safe_int(definition.get("first_deadline_days"),7)+1);forced=max(overdue+1,safe_int(definition.get("second_deadline_days"),23)+1)
    fine = {
        "id": f"fine_{source}_{uuid.uuid4().hex[:12]}",
        "source": source,
        "source_name": fine_source_label(source),
        "created_at_ts": created_at,
        "updated_at_ts": created_at,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(created_at)),
        "start_day": 1,
        "current_day": 1,
        "base_amount": base_amount,
        "current_amount": base_amount,
        "currency": str(definition.get("currency") or "copper"),
        "status": FINE_STATUS_VOLUNTARY,
        "last_interest_applied_day": max(0,safe_int(definition.get("interest_start_day"),overdue)-1),
        "first_deadline_day": overdue-1,"due_day": overdue-1,"overdue_day": overdue,"second_start_day": overdue,
        "second_deadline_day": forced-1,"third_start_day": forced,"forced_collection_day": forced,
        "daily_interest_percent": float(definition.get("interest_percent_per_day") or 1),"interest_start_day":safe_int(definition.get("interest_start_day"),overdue),"interest_enabled":bool(definition.get("interest_enabled",True)),
        "created_by": "raid",
        "restrictions":list(definition.get("restrictions") or []),"messages":dict(definition.get("messages") or {}),"stages":list(definition.get("stages") or []),"payment_places":list(definition.get("payment_places") or ["city","fortress"]),"payment_commission":safe_int(definition.get("payment_commission"),0),"payment_formula_id":definition.get("payment_formula_id"),"fortress_id":definition.get("fortress_id"),"city_id":definition.get("city_id"),"consequences":list(definition.get("consequences") or []),
        "can_pay":bool(definition.get("can_pay",True)),"partial_payment_allowed":bool(definition.get("partial_payment_allowed")),"payment_location_id":definition.get("payment_location_id"),"payment_sublocation_id":definition.get("payment_sublocation_id"),
        "movement_restricted": False,
        "can_pay_in_city_hall": True,
        "can_pay_in_fortress_hall": False,
        "paid_at": None,
        "notified_stages": [],
        "level_bonus_percent": calculate_level_bonus_percent(safe_int(player.get("level"), 1)),
    }
    fines = active_fines(player)
    fines.append(fine)
    player["active_fines"] = fines
    _sync_active_fine_alias(player)
    _history(player,"fine_created",fine,created_at_ts=created_at)
    try:
        from services.quest_runtime_service import progress as quest_progress
        quest_progress(player,"get_fine",source,1)
    except Exception:pass
    for row in fine.get("consequences") or []:
        if not isinstance(row,dict):continue
        kind=str(row.get("type") or "");oid=str(row.get("object_id") or "");amount=safe_int(row.get("amount"),0)
        if kind in {"reputation","hidden_reputation"} and oid:
            bucket=player.setdefault("hidden_reputations" if kind=="hidden_reputation" else "reputations",{});bucket[oid]=safe_int(bucket.get(oid),0)+amount
        elif kind in {"effect","curse"} and oid:player.setdefault("active_effects",[]).append({"effect_id":oid,"source":"fine","fine_id":fine["id"]})
        elif kind=="event" and oid:player["constructor_event_id"]=oid
    try:
        from services.achievement_engine import record_game_event
        record_game_event(player, "get_fine", 1, source)
        from services.reputation_runtime_service import apply_trigger
        apply_trigger(player, "fine_unpaid", source)
    except Exception:
        pass
    return fine


def source_for_raid_action(player: dict[str, Any], action: str) -> str | None:  # type: ignore[override]
    action = str(action or "").strip()
    if action in RAID_ACTION_SOURCES:
        return RAID_ACTION_SOURCES[action]
    zone = str(player.get("current_zone") or player.get("location_id") or "")
    if zone.startswith("seldar_npc_market_black"):
        return "black_market"
    context = player.get("market_context") if isinstance(player.get("market_context"), dict) else {}
    if str(context.get("market_kind") or "") == "black" and action not in {"Тёмные переулки", "Портовый квартал", "⬅️ Центральная площадь", "Центральная площадь"}:
        return "black_market"
    if zone in RAID_ZONE_SOURCES and action not in {"Портовый квартал", "⬅️ Центральная площадь", "Центральная площадь"}:
        return RAID_ZONE_SOURCES[zone]
    return None


def maybe_trigger_raid(  # type: ignore[override]
    player: dict[str, Any],
    action: str,
    rng: random.Random | Any | None = None,
    now: float | int | None = None,
) -> FineActionResult | None:
    source = source_for_raid_action(player, action)
    if not source:
        return None
    if not should_trigger_raid(rng):
        return None

    fine = create_raid_fine(player, source, now=now)
    advance_fine_state(player, now=now)
    move_player_to_central_square(player)
    amount = safe_int(fine.get("current_amount"), BASE_FINE_COPPER)
    total = sum(max(0, safe_int(item.get("current_amount"), 0)) for item in active_fines(player))
    count = len(active_fines(player))
    text = _format_raid_text(amount)
    text = _fine_text(fine,"on_issue",text)
    if count > 1:
        text += f"\n\nТеперь у вас активных штрафов: {count}. Общая сумма: {total} медных монет."
    return FineActionResult(
        text=text,
        buttons=_central_square_buttons(),
        zone_id="seldar_central_square",
    )


def _advance_one_fine(fine: dict[str, Any], now: float | int | None = None) -> tuple[bool, list[str], str]:
    changed = False
    messages: list[str] = []
    day = current_fine_day(fine, now=now)
    if safe_int(fine.get("current_day"), 1) != day:
        fine["current_day"] = day
        changed = True
    if _apply_interest_until(fine, day):
        changed = True
    authored=[row for row in fine.get("stages") or [] if isinstance(row,dict)]
    active_stage=None
    if authored:
        cursor=1
        for index,row in enumerate(authored):
            if day>=cursor:active_stage=(index,row)
            duration=max(0,safe_int(row.get("duration_days"),0));cursor+=duration
        index,row=active_stage or (0,authored[0]);applied=set(safe_int(x,-1) for x in fine.get("applied_stage_indexes") or [])
        if index not in applied:
            old=max(0,safe_int(fine.get("current_amount"),0));base=safe_int(row.get("base_amount"),0);fine["current_amount"]=base if base>0 else math.floor(old*(1+max(0,float(row.get("percent_increase") or 0))/100))+max(0,safe_int(row.get("per_day_increase"),0));applied.add(index);fine["applied_stage_indexes"]=sorted(applied);changed=True
            if row.get("text"):messages.append(str(row["text"]))
        fine["current_stage"]=str(row.get("stage") or index);codes={str(x.get("code") if isinstance(x,dict) else x) for x in fine.get("restrictions") or []}
        if row.get("block_city"):codes.add("block_city")
        if row.get("block_starting"):codes.add("block_starting")
        if row.get("force_fortress"):codes.add("force_fortress")
        fine["restrictions"]=[{"code":code} for code in sorted(codes)]
        stage_name=str(row.get("stage") or "");status=FINE_STATUS_FORCED if stage_name in {"third","permanent","special"} or row.get("force_fortress") or row.get("permanent") else FINE_STATUS_OVERDUE if stage_name=="second" or index>0 else FINE_STATUS_VOLUNTARY
    else:status = FINE_STATUS_FORCED if day>=safe_int(fine.get("forced_collection_day"),24) else FINE_STATUS_OVERDUE if day>=safe_int(fine.get("overdue_day"),8) else FINE_STATUS_VOLUNTARY
    if fine.get("status") != status:
        fine["status"] = status
        changed = True
    fine["movement_restricted"] = status == FINE_STATUS_FORCED
    fine["can_pay_in_city_hall"] = status in {FINE_STATUS_VOLUNTARY, FINE_STATUS_OVERDUE}
    fine["can_pay_in_fortress_hall"] = status == FINE_STATUS_FORCED
    amount = max(0, safe_int(fine.get("current_amount"), 0))
    if day >= 8:
        text = _notice_once(fine, "first_deadline", _first_deadline_letter(amount))
        if text:
            messages.append(text)
            changed = True
    if day >= 24:
        text = _notice_once(fine, "second_deadline", _second_deadline_letter(amount))
        if text:
            messages.append(text)
            changed = True
        text = _notice_once(fine, "third_start", _third_start_letter(amount))
        if text:
            messages.append(text)
            changed = True
    return changed, messages, status


def advance_fine_state(player: dict[str, Any], now: float | int | None = None) -> FineAdvanceResult:  # type: ignore[override]
    fines = active_fines(player)
    if not fines:
        return FineAdvanceResult()
    changed = False
    messages: list[str] = []
    forced = False
    for fine in fines:
        old_status=str(fine.get("status") or FINE_STATUS_VOLUNTARY);old_amount=safe_int(fine.get("current_amount"),0);old_restricted=bool(fine.get("movement_restricted"))
        item_changed, item_messages, status = _advance_one_fine(fine, now=now)
        changed = changed or item_changed
        messages.extend(item_messages)
        forced = forced or status == FINE_STATUS_FORCED
        if status!=old_status:_history(player,"fine_status_changed",fine,old_status=old_status,new_status=status)
        if safe_int(fine.get("current_amount"),0)!=old_amount:_history(player,"fine_interest_added",fine,old_amount=old_amount,new_amount=safe_int(fine.get("current_amount"),0))
        if bool(fine.get("movement_restricted"))!=old_restricted:_history(player,"movement_restriction_enabled" if fine.get("movement_restricted") else "movement_restriction_disabled",fine)
    moved = False
    if forced and _is_city_or_starting_location(player):
        move_player_to_fortress(player)
        messages.append(_forced_move_text())
        moved = True
        changed = True
    _sync_active_fine_alias(player)
    return FineAdvanceResult(messages=tuple(messages), moved_to_fortress=moved, changed=changed)


def is_forced_collection(player: dict[str, Any]) -> bool:  # type: ignore[override]
    return any(str(fine.get("status") or "") == FINE_STATUS_FORCED for fine in active_fines(player))


def _fine_lines_for_card(fines: list[dict[str, Any]], now: float | int | None = None) -> list[str]:
    lines: list[str] = []
    for index, fine in enumerate(fines, 1):
        day = current_fine_day(fine, now=now)
        status = str(fine.get("status") or FINE_STATUS_VOLUNTARY)
        amount = safe_int(fine.get("current_amount"), 0)
        if status == FINE_STATUS_VOLUNTARY:
            next_stage = "просрочка на 8-й день"
            days_left = max(0, 8 - day)
        elif status == FINE_STATUS_OVERDUE:
            next_stage = "принудительное взыскание на 24-й день"
            days_left = max(0, 24 - day)
        else:
            next_stage = "бессрочно до оплаты"
            days_left = 0
        lines.append(
            f"{index}. {fine.get('source_name') or fine_source_label(fine.get('source'))}: "
            f"{amount} медных, {fine_status_label(status)}, день {day}, следующий этап: {next_stage}, осталось: {days_left} дн."
        )
    return lines


def fine_card(player: dict[str, Any], *, place: str = "city", now: float | int | None = None) -> FineActionResult:  # type: ignore[override]
    advance_fine_state(player, now=now)
    fines = active_fines(player)
    zone_id = "seldar_town_manager" if place == "city" else "fortress_in_gorge_fortress_hall"
    back = CITY_HALL_BACK if place == "city" else FORTRESS_BACK
    if not fines:
        return FineActionResult("В городской книге долгов на ваше имя нет активных штрафов.", [[back]], zone_id)
    total = sum(max(0, safe_int(fine.get("current_amount"), 0)) for fine in fines)
    lines = [
        "Городские штрафы",
        "",
        f"Активных штрафов: {len(fines)}",
        f"Общая сумма: {total} медных монет",
        "Ежедневные проценты: со 2-го срока +1% ежедневно",
        "",
        *_fine_lines_for_card(fines, now=now),
        "",
        "Оплатить доступные штрафы?",
    ]
    return FineActionResult("\n".join(lines), [[CITY_FINE_PAY_ACTION], [back]], zone_id)


def pay_fine(player: dict[str, Any], *, place: str, now: float | int | None = None) -> FineActionResult:  # type: ignore[override]
    advance_fine_state(player, now=now)
    fines = active_fines(player)
    zone_id = "seldar_town_manager" if place == "city" else "fortress_in_gorge_fortress_hall"
    back = CITY_HALL_BACK if place == "city" else FORTRESS_BACK
    if not fines:
        return FineActionResult("В городской книге долгов на ваше имя нет активных штрафов.", [[back]], zone_id)
    if place == "city":
        payable = [fine for fine in fines if fine.get("can_pay",True) and str(fine.get("status") or FINE_STATUS_VOLUNTARY) in {FINE_STATUS_VOLUNTARY, FINE_STATUS_OVERDUE} and "city" in (fine.get("payment_places") or ["city","fortress"])]
        if not payable:
            return FineActionResult(
                _fine_text(fines[0],"impossible_payment","Управляющий просматривает книгу взысканий и медленно закрывает её.\n\n"
                "— Все ваши активные дела уже переданы крепостной администрации. Здесь я больше не могу принять оплату."),
                [[back]],
                zone_id,
            )
    else:
        payable = [fine for fine in fines if fine.get("can_pay",True) and str(fine.get("status") or "") == FINE_STATUS_FORCED and "fortress" in (fine.get("payment_places") or ["city","fortress"])]
        if not payable:
            return FineActionResult(
                _fine_text(fines[0],"impossible_payment","Крепостной Управляющий проверяет записи и качает головой.\n\n"
                "— Эти дела ещё числятся за городом. Пока взыскание не передано крепости, оплату принимает городской Управляющий."),
                [[back]],
                zone_id,
            )
    amount = 0
    for fine in payable:
        current=max(0,safe_int(fine.get("current_amount"),0));commission=max(0,safe_int(fine.get("payment_commission"),0));priced=current+commission
        if fine.get("payment_formula_id"):
            try:
                from services.formula_runtime import evaluate
                priced=max(0,safe_int(evaluate(fine["payment_formula_id"],{"base_amount":current,"commission":commission,"fine_day":fine.get("current_day",1)},default=priced),priced))
            except Exception:pass
        amount+=priced
    try:
        from services.economy_runtime import service_price
        amount=service_price("fine_payment",amount,player,{"location_id":zone_id,"fine_count":len(payable)})
    except (ImportError,ValueError):pass
    balance = _money(player)
    if balance < amount:
        return FineActionResult(
            _fine_text(payable[0],"insufficient_money",f"Недостаточно медных монет для оплаты штрафов. Нужно: {amount} медных монет. На балансе: {balance}.",required=amount,balance=balance),
            [[back]],
            zone_id,
        )
    _set_money(player, balance - amount)
    try:
        from services.economy_runtime import record
        record(player,"fine_payment","copper",-amount,balance,_money(player),source="fine",source_id=place)
    except (ImportError,OSError):pass
    paid_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_now_ts(now)))
    paid_ids = {str(fine.get("id") or "") for fine in payable}
    for fine in payable:
        fine["status"] = FINE_STATUS_PAID
        fine["paid_at"] = paid_at
        fine["movement_restricted"] = False
        fine["can_pay_in_city_hall"] = False
        fine["can_pay_in_fortress_hall"] = False
        player.setdefault("paid_fines", []).append(dict(fine))
        _history(player,"fine_paid",fine,place=place,created_at_ts=_now_ts(now))
    remaining = [fine for fine in fines if str(fine.get("id") or "") not in paid_ids and fine.get("status") != FINE_STATUS_PAID]
    player["active_fines"] = remaining
    _sync_active_fine_alias(player)
    remaining_forced = [fine for fine in remaining if str(fine.get("status") or "") == FINE_STATUS_FORCED]
    if place == "fortress":
        suffix = " Запрет снят." if not is_forced_collection(player) else ""
    elif remaining_forced:
        # На городском управляющем гасятся только добровольные/просроченные
        # штрафы. Бессрочные взыскания уже переданы крепости — без этого
        # пояснения игроку кажется, что деньги списались, а штраф «висит».
        total_forced = sum(max(0, safe_int(f.get("current_amount"), 0)) for f in remaining_forced)
        suffix = (
            f"\n\n⚠️ Остаются бессрочные взыскания: {len(remaining_forced)} шт. на "
            f"{total_forced} медных монет. Они уже переданы крепости и здесь не "
            "оплачиваются. Погасить их можно только в Крепостной Ратуше у "
            "Управляющего: Городские ворота → Крепость в ущелье → Крепостная ратуша."
        )
    elif not remaining:
        suffix = " Долг перед городом погашен."
    else:
        suffix = ""
    text = (
        "Управляющий сверяет записи в книге долгов.\n\n"
        f"Оплачено штрафов: {len(payable)}. Сумма: {amount} медных монет.\n\n"
        "Печати поставлены, оплаченные взыскания закрыты."
        f"{suffix}"
    )
    if len(payable)==1:text=_fine_text(payable[0],"on_pay",text,paid_amount=amount)
    try:
        from services.achievement_engine import record_game_event
        record_game_event(player, "pay_fine", len(payable), place)
        record_game_event(player, "spend_currency", amount, "copper")
        from services.reputation_runtime_service import apply_trigger
        for fine in payable:
            apply_trigger(player, "fine_paid", str(fine.get("source") or fine.get("id") or ""))
            from services.quest_runtime_service import progress as quest_progress
            quest_progress(player,"pay_penalty",str(fine.get("source") or fine.get("id") or ""),1)
    except Exception:
        pass
    return FineActionResult(text, [[back]], zone_id)

def remove_player_fine(player:dict[str,Any],fine_id:str,*,by:str="admin",reason:str="",delete:bool=False)->dict[str,Any]:
    """Remove one active or malformed fine; hard delete remains auditable."""
    candidates=[]
    if isinstance(player.get("active_fines"),list):candidates.extend(row for row in player["active_fines"] if isinstance(row,dict))
    if isinstance(player.get("active_fine"),dict):candidates.append(player["active_fine"])
    target=next((row for row in candidates if str(row.get("id") or "")==str(fine_id)),None)
    if target is None:raise ValueError("Штраф игрока не найден.")
    if not delete:
        record=dict(target);record.update({"status":FINE_STATUS_REMOVED,"removed_by":by,"removed_reason":reason});player.setdefault("removed_fines",[]).append(record)
    player["active_fines"]=[row for row in candidates if row is not target and str(row.get("id") or "")!=str(fine_id) and is_fine_active(row)]
    _sync_active_fine_alias(player);_history(player,"fine_invalid_dropped" if delete else "fine_removed_by_admin",target,by=by,reason=reason)
    return {"removed":1,"deleted":bool(delete),"fine_id":fine_id}

def pay_fine_amount(player:dict[str,Any],fine_id:str,amount:int,*,place:str="profile",now:float|int|None=None)->dict[str,Any]:
    fine=next((row for row in active_fines(player) if str(row.get("id") or "")==str(fine_id)),None)
    if not fine:raise ValueError("Штраф не найден.")
    if not fine.get("partial_payment_allowed"):raise ValueError("Частичная оплата этого штрафа запрещена.")
    if place not in (fine.get("payment_places") or []):raise ValueError("В этом месте штраф оплатить нельзя.")
    amount=max(1,safe_int(amount,0));due=max(0,safe_int(fine.get("current_amount"),0));paid=min(amount,due)
    if _money(player)<paid:raise ValueError("Недостаточно медных монет.")
    _set_money(player,_money(player)-paid);fine["current_amount"]=due-paid;_history(player,"fine_partial_paid",fine,place=place,paid_amount=paid,created_at_ts=_now_ts(now))
    closed=fine["current_amount"]<=0
    if closed:
        fine["status"]=FINE_STATUS_PAID;player.setdefault("paid_fines",[]).append(dict(fine));player["active_fines"]=[row for row in active_fines(player) if row is not fine];_sync_active_fine_alias(player);_history(player,"fine_paid",fine,place=place,created_at_ts=_now_ts(now))
    return {"paid":paid,"remaining":max(0,safe_int(fine.get("current_amount"),0)),"closed":closed}


def fine_entries_for_profile(player: dict[str, Any], now: float | int | None = None) -> list[dict[str, Any]]:
    """Structured active fines for the profile popup: number, amount, term.

    ``amount`` is denomination-formatted (e.g. «1 серебряная 200 медных»);
    ``term`` describes the remaining срок of the fine before the next stage.
    """
    from services.currency import format_price

    advance_fine_state(player, now=now)
    fines = active_fines(player)
    entries: list[dict[str, Any]] = []
    for index, fine in enumerate(fines, 1):
        day = current_fine_day(fine, now=now)
        status = str(fine.get("status") or FINE_STATUS_VOLUNTARY)
        amount = max(0, safe_int(fine.get("current_amount"), 0))
        if status == FINE_STATUS_VOLUNTARY:
            days_left = max(0, 8 - day)
            term = f"осталось {days_left} дн. до просрочки"
        elif status == FINE_STATUS_OVERDUE:
            days_left = max(0, 24 - day)
            term = f"осталось {days_left} дн. до взыскания"
        else:
            term = "бессрочно до оплаты"
        entries.append({
            "number": index,
            "source": fine.get("source_name") or fine_source_label(fine.get("source")),
            "amountCopper": amount,
            "amount": format_price(amount),
            "term": term,
            "status": fine_status_label(status),
            "day": day,
            "currency": str(fine.get("currency") or "copper"),
            "stage": str(fine.get("current_stage") or status),
            "createdAt": fine.get("created_at"),
            "permanent": status == FINE_STATUS_FORCED or str(fine.get("current_stage") or "") == "permanent",
            "paymentPlaces": list(fine.get("payment_places") or (["fortress"] if status == FINE_STATUS_FORCED else ["city"])),
            "restrictions": [str(row.get("code") if isinstance(row,dict) else row) for row in fine.get("restrictions") or []],
            "consequences": [str(row.get("text") or row.get("type") or "") for row in fine.get("consequences") or [] if isinstance(row,dict)],
        })
    return entries


def forgive_all_fines(player: dict[str, Any], *, by: str = "admin", reason: str = "", now: float | int | None = None) -> dict[str, Any]:
    """Снять ВСЕ активные штрафы игрока и все связанные ограничения (ТЗ §4/§5).

    Единый авторитетный путь снятия штрафов админом: помечает каждый активный
    штраф статусом removed_by_admin, переносит его в историю, чистит active_fines
    и legacy-алиас. Ограничения (forced-взыскание/запрет передвижения) выводятся
    из active_fines, поэтому их очистка автоматически снимает запрет — отдельных
    скрытых флагов нет. Возвращает отчёт {removed, was_forced}."""
    active = list(active_fines(player))
    was_forced = any(str(f.get("status") or "") == FINE_STATUS_FORCED for f in active)
    removed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_now_ts(now)))
    removed_bucket = player.setdefault("removed_fines", [])
    history = player.setdefault("fine_history", [])
    for fine in active:
        record = dict(fine)
        record["status"] = FINE_STATUS_REMOVED
        record["removed_at"] = removed_at
        record["removed_by"] = str(by or "admin")
        record["removed_reason"] = str(reason or "")
        record["movement_restricted"] = False
        removed_bucket.append(record)
        history.append({
            "fine_id": fine.get("id"),
            "event": FINE_STATUS_REMOVED,
            "by": str(by or "admin"),
            "reason": str(reason or ""),
            "at": removed_at,
            "amount": safe_int(fine.get("current_amount"), 0),
        })
    player["active_fines"] = []
    player.pop("active_fine", None)
    return {"removed": len(active), "was_forced": was_forced}


def repair_player_fines(player: dict[str, Any], now: float | int | None = None) -> dict[str, Any]:
    """Привести штрафы игрока в консистентное состояние (ТЗ §6/§7).

    Чинит «зависшие» данные: убирает из active_fines терминальные (оплаченные/
    снятые/истёкшие/отменённые) и битые записи, сбрасывает устаревший legacy-
    алиас, синхронизирует active_fine. Возвращает отчёт с диагнозом и списком
    исправлений (не двигает игрока — это чистая реконсиляция данных)."""
    issues: list[str] = []
    raw = player.get("active_fines")
    if isinstance(raw, list):
        cleaned = [f for f in raw if is_fine_active(f)]
        if len(cleaned) != len(raw):
            issues.append("dropped_inactive_or_invalid_fines")
            for dropped in raw:
                if not is_fine_active(dropped):_history(player,"fine_invalid_dropped",dropped if isinstance(dropped,dict) else None)
        player["active_fines"] = cleaned
    elif raw is not None:
        player["active_fines"] = []
        issues.append("reset_malformed_active_fines")

    legacy = player.get("active_fine")
    if legacy is not None and not is_fine_active(legacy):
        player.pop("active_fine", None)
        issues.append("dropped_inactive_legacy_alias")
    elif is_fine_active(legacy):
        # Legacy-форма: активный штраф лежит ТОЛЬКО в active_fine, списка
        # active_fines нет. Помечаем перенос — active_fines() ниже мигрирует
        # его в список. Без этого _sync_active_fine_alias затёр бы валидный
        # долг пустым списком (тихо снимал бы штраф и сообщал fixed: false).
        current = player.get("active_fines")
        current = current if isinstance(current, list) else []
        legacy_id = str(legacy.get("id") or "")
        if not legacy_id or all(str(f.get("id") or "") != legacy_id for f in current):
            issues.append("migrated_legacy_fine")

    # active_fines() переносит активный legacy active_fine в список И
    # синхронизирует алиас — вызываем ЕГО, а не голый _sync_active_fine_alias.
    fines = active_fines(player)
    seen:set[str]=set();repaired=[]
    for fine in list(fines):
        old_source=str(fine.get("source") or "");source=normalize_fine_source(old_source,fine.get("source_name"));fine["source"]=source;fine["source_name"]=SOURCE_NAMES.get(source,fine_source_label(source));
        if source!=old_source:issues.append("normalized_source_alias")
        fine.setdefault("id",f"fine_{source}_{uuid.uuid4().hex[:12]}");fid=str(fine.get("id") or "")
        if fid in seen:issues.append("removed_duplicate_fine");_history(player,"fine_duplicate_removed",fine);continue
        seen.add(fid)
        fine.setdefault("status",FINE_STATUS_VOLUNTARY);fine.setdefault("currency","copper");fine.setdefault("created_at_ts",_now_ts(now));fine.setdefault("updated_at_ts",_now_ts(now));fine.setdefault("current_day",current_fine_day(fine,now));fine.setdefault("due_day",7);fine.setdefault("overdue_day",8);fine.setdefault("forced_collection_day",24);fine.setdefault("daily_interest_percent",1);fine.setdefault("movement_restricted",fine.get("status")==FINE_STATUS_FORCED);fine.setdefault("can_pay_in_city_hall",fine.get("status") in {FINE_STATUS_VOLUNTARY,FINE_STATUS_OVERDUE});fine.setdefault("can_pay_in_fortress_hall",fine.get("status")==FINE_STATUS_FORCED)
        if fine.get("current_amount") in (None,""):
            fine["current_amount"]=safe_int(fine.get("base_amount"),0) or calculate_fine_amount(player,source);issues.append("restored_amount")
        fine.setdefault("base_amount",fine.get("current_amount"));repaired.append(fine)
    player["active_fines"]=repaired;_sync_active_fine_alias(player);fines=repaired
    if issues:_history(player,"fine_repaired",None,issues=list(dict.fromkeys(issues)))
    if not fines:
        state = "no_active_fines"
    elif is_forced_collection(player):
        state = "forced_active"
    else:
        state = "active_ok"
    return {"state": state, "issues": issues, "active_count": len(fines), "fixed": bool(issues)}


def fine_summary_for_profile(player: dict[str, Any], now: float | int | None = None) -> str:
    advance_fine_state(player, now=now)
    fines = active_fines(player)
    if not fines:
        return "нет активных штрафов"
    total = sum(max(0, safe_int(fine.get("current_amount"), 0)) for fine in fines)
    compact = []
    for fine in fines[:3]:
        compact.append(
            f"{fine.get('source_name') or fine_source_label(fine.get('source'))}: "
            f"{safe_int(fine.get('current_amount'), 0)} медных, {fine_status_label(str(fine.get('status') or FINE_STATUS_VOLUNTARY))}"
        )
    more = f"; ещё {len(fines) - 3}" if len(fines) > 3 else ""
    return f"{len(fines)} активн.; всего {total} медных; " + "; ".join(compact) + more
