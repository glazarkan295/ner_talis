"""Raid, city fine and movement restriction runtime for illegal Seldar activities."""

from __future__ import annotations

import math
import random
import time
import uuid
from dataclasses import dataclass
from typing import Any

from services.derived_stats_service import safe_int

RAID_CHANCE_PERCENT = 15
BASE_FINE_COPPER = 100
SECONDS_PER_FINE_DAY = 24 * 60 * 60
DAILY_INTEREST_PERCENT = 1

FINE_STATUS_VOLUNTARY = "voluntary"
FINE_STATUS_OVERDUE = "overdue"
FINE_STATUS_FORCED = "forced_collection"
FINE_STATUS_PAID = "paid"

CITY_FINE_SOURCE_LABELS = {
    "black_market": "Чёрный рынок",
    "informer_krot": "Информатор Крот",
    "underground_casino": "Подпольное казино",
}

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


def calculate_fine_amount(player: dict[str, Any]) -> int:
    level_bonus_percent = calculate_level_bonus_percent(safe_int(player.get("level"), 1))
    return max(BASE_FINE_COPPER, math.floor(BASE_FINE_COPPER * (1 + level_bonus_percent / 100)))


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
    base_amount = calculate_fine_amount(player)
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
            buttons=[["Верхний квартал"], ["Портовый квартал"], ["Торговый квартал"]],
            zone_id="seldar_central_square",
        )

    fine = create_raid_fine(player, source, now=now)
    move_player_to_central_square(player)
    amount = safe_int(fine.get("current_amount"), BASE_FINE_COPPER)
    return FineActionResult(
        text=_format_raid_text(amount),
        buttons=[["Верхний квартал"], ["Портовый квартал"], ["Торговый квартал"]],
        zone_id="seldar_central_square",
    )


def _apply_interest_until(fine: dict[str, Any], current_day: int) -> bool:
    last_day = safe_int(fine.get("last_interest_applied_day"), 7)
    if current_day < 8:
        fine["last_interest_applied_day"] = max(last_day, 7)
        return False
    changed = False
    for _day in range(max(8, last_day + 1), current_day + 1):
        amount = max(0, safe_int(fine.get("current_amount"), 0))
        fine["current_amount"] = math.floor(amount * 1.01)
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


def pay_fine(player: dict[str, Any], *, place: str, now: float | int | None = None) -> FineActionResult:
    advance_fine_state(player, now=now)
    fine = _fine(player)
    zone_id = "seldar_town_hall" if place == "city" else "fortress_in_gorge_fortress_hall"
    back = CITY_HALL_BACK if place == "city" else FORTRESS_BACK
    if fine is None:
        return FineActionResult("В городской книге долгов на ваше имя нет активных штрафов.", [[back]], zone_id)
    status = str(fine.get("status") or FINE_STATUS_VOLUNTARY)
    if place == "city" and status == FINE_STATUS_FORCED:
        return FineActionResult(
            "Управляющий просматривает книгу взысканий и медленно закрывает её.\n\n"
            "— Ваше дело уже передано крепостной администрации. Здесь я больше не могу принять оплату.\n\n"
            "Штраф теперь можно погасить только в Крепостной Ратуше, у Управляющего в Крепости в ущелье.",
            [[back]],
            zone_id,
        )
    if place == "fortress" and status != FINE_STATUS_FORCED:
        return FineActionResult(
            "Крепостной Управляющий проверяет записи и качает головой.\n\n"
            "— Это дело ещё числится за городом. Пока взыскание не передано крепости, оплату принимает Управляющий в городской Ратуше.",
            [[back]],
            zone_id,
        )
    amount = max(0, safe_int(fine.get("current_amount"), 0))
    balance = _money(player)
    if balance < amount:
        return FineActionResult(
            f"Недостаточно медных монет для оплаты штрафа. Штраф составляет {amount} медных монет.",
            [[back]],
            zone_id,
        )
    _set_money(player, balance - amount)
    fine["status"] = FINE_STATUS_PAID
    fine["paid_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_now_ts(now)))
    fine["movement_restricted"] = False
    fine["can_pay_in_city_hall"] = False
    fine["can_pay_in_fortress_hall"] = False
    player.setdefault("paid_fines", []).append(dict(fine))
    player.pop("active_fine", None)
    if place == "fortress":
        text = (
            "Крепостной Управляющий поднимает взгляд от тяжёлой книги взысканий.\n\n"
            f"— Долг перед городом передан нам. Сумма с процентами: {amount} медных монет.\n\n"
            "Вы выплачиваете штраф. Управляющий пересчитывает монеты, ставит печать и делает короткую отметку в книге.\n\n"
            "— Запрет снят. Можешь возвращаться в город и стартовые земли."
        )
    else:
        text = (
            "Управляющий неторопливо сверяет вашу запись в городской книге долгов.\n\n"
            f"— Штраф найден. Сумма к оплате: {amount} медных монет.\n\n"
            "Вы передаёте нужную сумму. Управляющий ставит печать на странице и закрывает книгу.\n\n"
            "— Долг перед городом погашен. В следующий раз советую выбирать места для сделок осторожнее."
        )
    return FineActionResult(text, [[back]], zone_id)

# --- Multi-fine v2 helpers -------------------------------------------------
# Re-defined near the end intentionally: legacy save files used ``active_fine``;
# new logic stores all active fines in ``active_fines`` and keeps active_fine as
# a compatibility alias for the first unpaid fine.

def active_fines(player: dict[str, Any]) -> list[dict[str, Any]]:
    fines: list[dict[str, Any]] = []
    raw = player.get("active_fines")
    if isinstance(raw, list):
        for fine in raw:
            if isinstance(fine, dict) and fine.get("status") != FINE_STATUS_PAID:
                fines.append(fine)
    legacy = player.get("active_fine")
    if isinstance(legacy, dict) and legacy.get("status") != FINE_STATUS_PAID:
        legacy_id = str(legacy.get("id") or "")
        if not legacy_id or all(str(f.get("id") or "") != legacy_id for f in fines):
            fines.append(legacy)
    player["active_fines"] = fines
    _sync_active_fine_alias(player)
    return fines


def _sync_active_fine_alias(player: dict[str, Any]) -> None:
    fines = [fine for fine in player.get("active_fines", []) if isinstance(fine, dict) and fine.get("status") != FINE_STATUS_PAID]
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


def create_raid_fine(player: dict[str, Any], source: str, now: float | int | None = None) -> dict[str, Any]:  # type: ignore[override]
    created_at = _now_ts(now)
    base_amount = calculate_fine_amount(player)
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
    fines = active_fines(player)
    fines.append(fine)
    player["active_fines"] = fines
    _sync_active_fine_alias(player)
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
    if count > 1:
        text += f"\n\nТеперь у вас активных штрафов: {count}. Общая сумма: {total} медных монет."
    return FineActionResult(
        text=text,
        buttons=[["Верхний квартал"], ["Портовый квартал"], ["Торговый квартал"]],
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
    return changed, messages, status


def advance_fine_state(player: dict[str, Any], now: float | int | None = None) -> FineAdvanceResult:  # type: ignore[override]
    fines = active_fines(player)
    if not fines:
        return FineAdvanceResult()
    changed = False
    messages: list[str] = []
    forced = False
    for fine in fines:
        item_changed, item_messages, status = _advance_one_fine(fine, now=now)
        changed = changed or item_changed
        messages.extend(item_messages)
        forced = forced or status == FINE_STATUS_FORCED
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
        payable = [fine for fine in fines if str(fine.get("status") or FINE_STATUS_VOLUNTARY) in {FINE_STATUS_VOLUNTARY, FINE_STATUS_OVERDUE}]
        if not payable:
            return FineActionResult(
                "Управляющий просматривает книгу взысканий и медленно закрывает её.\n\n"
                "— Все ваши активные дела уже переданы крепостной администрации. Здесь я больше не могу принять оплату.",
                [[back]],
                zone_id,
            )
    else:
        payable = [fine for fine in fines if str(fine.get("status") or "") == FINE_STATUS_FORCED]
        if not payable:
            return FineActionResult(
                "Крепостной Управляющий проверяет записи и качает головой.\n\n"
                "— Эти дела ещё числятся за городом. Пока взыскание не передано крепости, оплату принимает городской Управляющий.",
                [[back]],
                zone_id,
            )
    amount = sum(max(0, safe_int(fine.get("current_amount"), 0)) for fine in payable)
    balance = _money(player)
    if balance < amount:
        return FineActionResult(
            f"Недостаточно медных монет для оплаты штрафов. Нужно: {amount} медных монет. На балансе: {balance}.",
            [[back]],
            zone_id,
        )
    _set_money(player, balance - amount)
    paid_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_now_ts(now)))
    paid_ids = {str(fine.get("id") or "") for fine in payable}
    for fine in payable:
        fine["status"] = FINE_STATUS_PAID
        fine["paid_at"] = paid_at
        fine["movement_restricted"] = False
        fine["can_pay_in_city_hall"] = False
        fine["can_pay_in_fortress_hall"] = False
        player.setdefault("paid_fines", []).append(dict(fine))
    remaining = [fine for fine in fines if str(fine.get("id") or "") not in paid_ids and fine.get("status") != FINE_STATUS_PAID]
    player["active_fines"] = remaining
    _sync_active_fine_alias(player)
    suffix = " Запрет снят." if place == "fortress" and not is_forced_collection(player) else ""
    text = (
        "Управляющий сверяет записи в книге долгов.\n\n"
        f"Оплачено штрафов: {len(payable)}. Сумма: {amount} медных монет.\n\n"
        "Печати поставлены, оплаченные взыскания закрыты. Долг перед городом погашен."
        f"{suffix}"
    )
    return FineActionResult(text, [[back]], zone_id)


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
