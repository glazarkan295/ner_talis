"""Мировые события V2 (ТЗ «Мировые события»). Слой данных + валидация.

Хранение через генерик EntityStore (data/world_events.json). Аудит и права — в
роутере (admin_community_api). Награды реально распределяются через
``distribute_rewards`` с idempotent claim на игроке и уведомлением очереди.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from services.admin_entity_store import EntityStore

# --- Статусы жизненного цикла события ---------------------------------------
STATUS_DRAFT = "draft"
STATUS_SCHEDULED = "scheduled"
STATUS_ACTIVE = "active"
STATUS_FINISHED = "finished"
STATUS_DISABLED = "disabled"
STATUS_ARCHIVE = "archive"

STATUSES = (
    STATUS_DRAFT, STATUS_SCHEDULED, STATUS_ACTIVE,
    STATUS_FINISHED, STATUS_DISABLED, STATUS_ARCHIVE,
)
STATUS_LABELS = {
    STATUS_DRAFT: "Черновик",
    STATUS_SCHEDULED: "Запланировано",
    STATUS_ACTIVE: "Активно",
    STATUS_FINISHED: "Завершено",
    STATUS_DISABLED: "Отключено",
    STATUS_ARCHIVE: "Архив",
}
TRANSITIONS: dict[str, set[str]] = {
    # Старт можно дать сразу из черновика (быстрый запуск админом), не только
    # после планирования.
    STATUS_DRAFT: {STATUS_SCHEDULED, STATUS_ACTIVE, STATUS_ARCHIVE},
    STATUS_SCHEDULED: {STATUS_ACTIVE, STATUS_DISABLED, STATUS_DRAFT, STATUS_ARCHIVE},
    STATUS_ACTIVE: {STATUS_FINISHED, STATUS_DISABLED, STATUS_ARCHIVE},
    STATUS_FINISHED: {STATUS_ARCHIVE},
    STATUS_DISABLED: {STATUS_SCHEDULED, STATUS_ACTIVE, STATUS_ARCHIVE},
    STATUS_ARCHIVE: set(),
}

EVENT_TYPES = (
    "global", "regional", "city", "location", "seasonal", "repeatable",
    "one_time", "weekly", "monthly", "yearly", "festive", "combat",
    "economic", "crafting", "weather", "zone", "story", "system",
    # Legacy definitions remain editable and executable.
    "permanent", "threat", "world_boss", "global_raid", "mob_invasion",
    "fair", "guild", "boosted_drop", "boosted_exp", "new_location",
)
# Лимиты временных множителей мира (ТЗ §15) — превышение блокирует публикацию.
MAX_WORLD_MULTIPLIER = 5.0

# Типы повтора события (ТЗ §4.2): не только раз в год.
REPEAT_TYPES = ("none", "daily", "weekly", "monthly", "yearly")

# Типы наград мирового события (ТЗ §4.3).
REWARD_TYPES = (
    "experience", "coins", "item", "resource", "effect", "achievement",
    "special_loot", "temp_buff", "temp_debuff", "event_shop", "special_location", "energy", "skill_points", "stat_points", "recipe", "skill", "reputation",
)
# Источники особой добычи события (ТЗ §4.4).
SPECIAL_LOOT_SOURCES = (
    "all_mobs", "selected_mobs", "all_events", "selected_events", "locations",
    "search", "battle", "chest", "quest", "camp", "fishing", "gather", "special",
)
# Привязка выпадения предметов мирового события к локациям (доп. ТЗ §2.3).
LOCATION_BINDINGS = (
    "none", "all", "selected", "city", "fortress", "external", "dangerous", "starting",
)
MODIFIER_TYPES = ("event_chance","mob_chance","elite_mob_chance","pvp_chance","pve_chance","drop_chance","resource_amount","buy_price","sell_price","commission","reward","experience","energy","energy_flat","rest_time","craft_time","craft_success","craft_success_percent","location_access","npc_access","active_zone","player_effect")
SCOPE_TYPES = ("world","region","city","location","sublocation","camp","market","npc","player_group","players","player")

_store = EntityStore(
    env_var="WORLD_EVENTS_PATH",
    default_rel="data/world_events.json",
    statuses=STATUSES,
    transitions=TRANSITIONS,
    initial_status=STATUS_DRAFT,
)


def store() -> EntityStore:
    return _store


def _has_markup(value: str) -> bool:
    low = value.lower()
    return "<script" in low or ("<" in value and ">" in value)


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    """Проверка события перед запуском (ТЗ §19, применимая часть)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not str(data.get("name") or "").strip():
        errors.append("Не заполнено название события.")
    ev_type = str(data.get("type") or "").strip()
    if ev_type and ev_type not in EVENT_TYPES:
        errors.append(f"Неизвестный тип события: {ev_type}.")

    start = _parse_date(data.get("start_date"))
    end = _parse_date(data.get("end_date"))
    if data.get("start_date") and start is None:
        errors.append("Некорректная дата начала.")
    if data.get("end_date") and end is None:
        errors.append("Некорректная дата окончания.")
    if start and end and end <= start:
        errors.append("Дата окончания должна быть позже даты начала.")
    if not data.get("start_date"):
        warnings.append("Не указана дата начала.")
    scope=str(data.get("scope_type") or "world")
    if scope not in SCOPE_TYPES:errors.append(f"Неизвестная область действия: {scope}.")
    if scope!="world" and not data.get("all_world") and not (data.get("scope_id") or data.get("scope_ids")):warnings.append("Для ограниченной области не заданы ID.")
    timezone_name=str(data.get("timezone") or "UTC")
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(timezone_name)
    except Exception:errors.append(f"Неизвестный часовой пояс: {timezone_name}.")
    if data.get("start_by_condition") and not data.get("start_condition"):errors.append("Для запуска по условию задайте условие старта.")
    if data.get("end_by_condition") and not data.get("end_condition"):errors.append("Для завершения по условию задайте условие завершения.")
    for i,row in enumerate(data.get("modifiers") or [],1):
        if not isinstance(row,dict):errors.append(f"Модификатор {i}: неверный формат.");continue
        typ=str(row.get("type") or "")
        if typ not in MODIFIER_TYPES:errors.append(f"Модификатор {i}: неизвестный тип «{typ}».")
        value=_num(row.get("value"))
        if value is None and not row.get("formula_id") and typ not in ("player_effect","location_access","npc_access","active_zone"):errors.append(f"Модификатор {i}: нужно значение или формула.")
        if str(row.get("value_mode") or "percent") not in ("percent","multiplier","number"):errors.append(f"Модификатор {i}: неизвестный режим значения.")
        if str(row.get("value_mode") or "") in ("multiplier","number") and value is not None and value>MAX_WORLD_MULTIPLIER and typ not in ("energy_flat","craft_success_percent"):errors.append(f"Модификатор {i}: множитель превышает {MAX_WORLD_MULTIPLIER}.")

    # Временные множители мира не должны превышать лимит.
    for key in ("exp_multiplier", "drop_multiplier", "coin_multiplier"):
        value = _num(data.get(key))
        if value is None:
            continue
        if value < 0:
            errors.append(f"Множитель «{key}» не может быть отрицательным.")
        elif value > MAX_WORLD_MULTIPLIER:
            errors.append(f"Множитель «{key}» превышает лимит ({MAX_WORLD_MULTIPLIER}).")

    # Повтор события (ТЗ §4.1/§4.2).
    if data.get("repeat_enabled"):
        rtype = str(data.get("repeat_type") or "").strip()
        if rtype and rtype not in REPEAT_TYPES:
            errors.append(f"Неизвестный тип повтора: {rtype}.")
        if rtype == "weekly":
            wd = _num(data.get("repeat_weekday"))
            if wd is None or wd < 0 or wd > 6:
                errors.append("День недели повтора должен быть 0–6 (Пн–Вс).")
        if rtype == "monthly":
            dom = _num(data.get("repeat_day_of_month"))
            if dom is None or dom < 1 or dom > 31:
                errors.append("День месяца повтора должен быть 1–31.")
        if rtype == "yearly":
            mon = _num(data.get("repeat_month"))
            if mon is not None and (mon < 1 or mon > 12):
                errors.append("Месяц повтора должен быть 1–12.")
        if rtype == "yearly":
            # Ежегодный повтор может задавать день начала/окончания и месяц окончания (§3.4).
            end_mon = _num(data.get("repeat_end_month"))
            if end_mon is not None and (end_mon < 1 or end_mon > 12):
                errors.append("Месяц окончания повтора должен быть 1–12.")
            for key in ("repeat_start_day", "repeat_end_day"):
                val = _num(data.get(key))
                if val is not None and (val < 1 or val > 31):
                    errors.append(f"День в «{key}» должен быть 1–31.")
        for key in ("repeat_start_hour", "repeat_end_hour"):
            val = _num(data.get(key))
            if val is not None and (val < 0 or val > 23):
                errors.append(f"Час в «{key}» должен быть 0–23.")
        # Длительность события в днях (§3.1) — неотрицательная.
        dur = _num(data.get("repeat_duration_days"))
        if data.get("repeat_duration_days") not in (None, "") and (dur is None or dur < 0):
            errors.append("Длительность события (дней) не может быть отрицательной.")

    # Награды события (ТЗ §4.3).
    rewards = data.get("rewards")
    if isinstance(rewards, list):
        for i, row in enumerate(rewards, 1):
            if not isinstance(row, dict):
                errors.append(f"Награда {i}: неверный формат.")
                continue
            rtype = str(row.get("type") or "").strip()
            if rtype and rtype not in REWARD_TYPES:
                errors.append(f"Награда {i}: неизвестный тип «{rtype}».")
            amt = _num(row.get("amount"))
            if amt is not None and amt < 0:
                errors.append(f"Награда {i}: количество не может быть отрицательным.")

    # Особая добыча события (ТЗ §4.4).
    special_loot = data.get("special_loot")
    if isinstance(special_loot, list):
        for i, row in enumerate(special_loot, 1):
            if not isinstance(row, dict):
                errors.append(f"Особая добыча {i}: неверный формат.")
                continue
            source = str(row.get("source") or "").strip()
            if source and source not in SPECIAL_LOOT_SOURCES:
                errors.append(f"Особая добыча {i}: неизвестный источник «{source}».")
            chance = _num(row.get("chance"))
            if chance is not None and (chance < 0 or chance > 100):
                errors.append(f"Особая добыча {i}: шанс должен быть 0–100.")
            mn = _num(row.get("min_count"))
            mx = _num(row.get("max_count"))
            if mn is not None and mx is not None and mn > mx:
                errors.append(f"Особая добыча {i}: мин. количество больше макс.")
            # Привязка к локациям (§2.3) и лимиты (§2.2).
            binding = str(row.get("location_binding") or "").strip()
            if binding and binding not in LOCATION_BINDINGS:
                errors.append(f"Особая добыча {i}: неизвестная привязка к локациям «{binding}».")
            for lim in ("per_player_limit", "total_limit"):
                val = _num(row.get(lim))
                if val is not None and val < 0:
                    errors.append(f"Особая добыча {i}: «{lim}» не может быть отрицательным.")

    if not str(data.get("start_message") or "").strip():
        warnings.append("Нет сообщения о начале события.")
    if not str(data.get("end_message") or "").strip():
        warnings.append("Нет сообщения о завершении события.")

    for key in ("name", "short_description", "description"):
        value = str(data.get(key) or "").strip()
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")

    # Вывод объявления игрокам (дополнение к ТЗ): изображение/формат/блоки.
    announce_message = data.get("announce_message")
    if announce_message:
        from services.message_output_service import validate_message_output
        result = validate_message_output(announce_message)
        errors.extend(f"Объявление — {e}" for e in result["errors"])
        warnings.extend(f"Объявление — {w}" for w in result["warnings"])

    return {"ok": not errors, "errors": errors, "warnings": warnings}


_CURRENCY_RATE = {"copper": 1, "silver": 1_000, "gold": 1_000_000,
                  "magic_gold": 1_000_000_000, "ancient_coin": 500_000_000_000}


def _grant_reward(player: dict[str, Any], reward: dict[str, Any], *, event_id: str = "", storage: Any = None) -> None:
    kind = str(reward.get("type") or "")
    object_id = str(reward.get("item_id") or reward.get("object_id") or "")
    amount = max(1, int(_num(reward.get("amount")) or 1))
    try:
        from services.world_event_runtime import modifiers
        mods=modifiers(context={"game_id":player.get("game_id"),"world_event_id":event_id})
        factor=float(mods.get("exp_multiplier" if kind=="experience" else "energy_multiplier" if kind=="energy" else "reward_multiplier",1) or 0)
        amount=max(1,int(amount*factor))
    except Exception:pass
    if kind == "experience":
        player["experience"] = int(player.get("experience") or 0) + amount
        player["total_experience"] = int(player.get("total_experience") or 0) + amount
    elif kind == "coins":
        currency = str(reward.get("currency") or object_id or "copper")
        amount *= _CURRENCY_RATE.get(currency, 1)
        try:
            from services.economy_runtime import change, reward_amount
            amount=reward_amount("event",amount,{"event_id":event_id})
            change(player,"copper",amount,operation="event_reward",source="world_event",source_id=event_id)
        except (ImportError, ValueError):
            player["money"] = int(player.get("money") or 0) + amount
    elif kind in ("item", "resource", "special_loot") and object_id:
        from services.inventory_service import add_inventory_item
        from services.item_registry import build_inventory_item
        add_inventory_item(player, build_inventory_item(object_id, amount, item_id=object_id), amount,
                           default_source="world_event")
    elif kind in ("effect", "temp_buff", "temp_debuff") and object_id:
        from services.effect_formula_runtime import apply_to_player
        apply_to_player(player, object_id, source="world_event")
    elif kind == "achievement" and object_id:
        if storage is not None:
            from services.achievement_engine import grant
            try:grant(storage,player,object_id,source="world_event",save=False)
            except ValueError:player.setdefault("achievement_progress", {})[object_id] = {"completed": True, "source": "world_event"}
        else:player.setdefault("achievement_progress", {})[object_id] = {"completed": True, "source": "world_event"}
    elif kind == "energy":player["energy"]=min(int(player.get("max_energy") or 100),int(player.get("energy") or 0)+amount)
    elif kind == "skill_points":player["free_skill_points"]=int(player.get("free_skill_points") or 0)+amount
    elif kind == "stat_points":player["free_stat_points"]=int(player.get("free_stat_points") or 0)+amount
    elif kind in ("recipe","skill") and object_id:player.setdefault("unlocks",{})[object_id]=True
    elif kind == "reputation" and object_id:
        from services.reputation_runtime_service import change
        change(player,object_id,amount,source="world_event",source_id=event_id)
    elif kind in ("special_location", "event_shop") and object_id:
        player.setdefault("unlocks", {})[object_id] = True


def distribute_rewards(storage: Any, event_id: str) -> dict[str, Any]:
    env = store().get(event_id)
    if env is None:
        raise ValueError("Событие не найдено.")
    data = env.get("data") or {}
    rewards = [r for r in data.get("rewards") or [] if isinstance(r, dict)]
    explicit = {str(x) for x in data.get("participant_ids") or [] if str(x)}
    rows = storage.list_player_audience_rows() if hasattr(storage, "list_player_audience_rows") else []
    game_ids = [str(row.get("game_id") or "") for row in rows if row.get("game_id")]
    if explicit:
        game_ids = [gid for gid in game_ids if gid in explicit]
    granted = skipped = missing = 0
    for game_id in game_ids:
        player = storage.get_player_by_game_id(game_id)
        if not isinstance(player, dict):
            missing += 1
            continue
        claims = player.get("world_event_reward_claims")
        claims = claims if isinstance(claims, list) else []
        claim_key = f"{event_id}:{env.get('version')}"
        if claim_key in claims:
            skipped += 1
            continue
        for reward in rewards:
            _grant_reward(player, reward, event_id=event_id, storage=storage)
        claims.append(claim_key)
        player["world_event_reward_claims"] = claims[-200:]
        try:
            from services.achievement_engine import record_game_event
            record_game_event(player, "join_world_event", 1, event_id, storage=storage)
            record_game_event(player, "finish_event", 1, event_id, storage=storage)
        except Exception:
            pass
        try:
            from services.reputation_runtime_service import apply_trigger
            apply_trigger(player, "world_event", event_id)
        except Exception:
            pass
        storage.update_player(player)
        try:
            from services.message_delivery import notify_player
            notify_player(storage, game_id, str(data.get("reward_message") or f"Награды события «{data.get('name') or event_id}» выданы."),
                          type="reward", priority="normal", source="world_event",
                          delivery_key=f"world_event:{claim_key}:{game_id}",
                          text_key="reward.received",
                          text_variables={"reward": str(data.get("name") or event_id)})
        except Exception:
            pass
        granted += 1
    return {"event_id": event_id, "granted": granted, "skipped": skipped, "missing": missing,
            "audience": len(game_ids), "reward_count": len(rewards)}
