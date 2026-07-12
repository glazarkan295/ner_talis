"""Profile API for the React website.

The React profile from ``web/`` talks to these endpoints. The module uses the
same storage factory as Telegram/VK, so it works with PostgreSQL, SQLite and
JSON without a separate data file.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services.derived_stats_service import (
    calculate_player_derived_stats,
    calculate_energy_stats,
    ceil,
    collect_modifiers_from_value,
    equipment_bonus,
    equipment_modifier_totals,
    equipment_stat_bonus,
    external_effect_modifier_totals,
    merge_modifier_totals,
    safe_int,
    ensure_player_resources,
    calculate_player_skill_raw_damage,
    prune_expired_effects,
)
from services.item_registry import enrich_inventory_item
from services.inventory_service import (
    add_inventory_item,
    is_levelled_equipment_item,
    max_overflow_slots,
    max_regular_slots,
    overflow_slot_count,
    recalculate_inventory_overflow,
    regular_slot_count,
)
from services.promo_service import redeem_promo_code
from services.fine_service import fine_entries_for_profile, fine_summary_for_profile
from services.market_service import (
    is_profile_market_sell_enabled,
    sell_item_from_profile,
    sellable_inventory_stack_indexes,
)
from services.web_profile import ADMIN_PROFILE_EDIT_SCOPE, PROFILE_SCOPE
from services.active_skill_service import refresh_unlocked_active_skills, resource_cost_with_modifiers, skill_level, is_skill_weapon_compatible, skill_weapon_requirement_text, can_spend_skill_points_on, skill_upgrade_cost, player_branch, selected_main_path, selected_secondary_path, path_level, secondary_path_limit
from services.small_plateau_service import ensure_curse_bearer_effect

FRONT_TO_BACK_STAT = {
    "strength": "strength",
    "endurance": "endurance",
    "agility": "dexterity",
    "dexterity": "dexterity",
    "perception": "perception",
    "intelligence": "intelligence",
    "wisdom": "wisdom",
}

ATTRIBUTE_META = [
    ("strength", "strength", "Сила", "Физический урон, пробой, блоки, силовые стойки."),
    ("endurance", "endurance", "Выносливость", "HP, физическая защита, дух, устойчивость."),
    ("agility", "dexterity", "Ловкость", "Уклонение, парирование, быстрые атаки."),
    ("perception", "perception", "Восприятие", "Точность, крит, обнаружение угроз."),
    ("intelligence", "intelligence", "Интеллект", "Магические навыки, мана, сложные формы."),
    ("wisdom", "wisdom", "Мудрость", "Поддержка, лечение, регенерация маны и устойчивые магические формы."),
]

EQUIPMENT_SLOTS = [
    {"key": "helmet", "label": "Шлем", "icon": "⛑", "positionClass": "slot-helmet"},
    {"key": "necklace", "label": "Ожерелье", "icon": "◆", "positionClass": "slot-necklace"},
    {"key": "chest", "label": "Нагрудник", "icon": "▣", "positionClass": "slot-chest"},
    {"key": "belt", "label": "Пояс", "icon": "▰", "positionClass": "slot-belt"},
    {"key": "pants", "label": "Штаны", "icon": "▥", "positionClass": "slot-pants"},
    {"key": "boots", "label": "Ботинки", "icon": "▱", "positionClass": "slot-boots"},
    {"key": "gloves", "label": "Перчатки", "icon": "✋", "positionClass": "slot-gloves"},
    {"key": "ring1", "label": "Кольцо 1", "icon": "○", "positionClass": "slot-ring1"},
    {"key": "ring2", "label": "Кольцо 2", "icon": "○", "positionClass": "slot-ring2"},
    {"key": "weapon1", "label": "Оружие 1", "icon": "⚔", "positionClass": "slot-weapon1"},
    {"key": "weapon2", "label": "Оружие 2", "icon": "🛡", "positionClass": "slot-weapon2"},
    {"key": "special", "label": "Особый слот", "icon": "✦", "positionClass": "slot-special"},
]

CRAFT_LABELS = {
    "smelting": "Плавильное дело",
    "blacksmithing": "Кузнечное дело",
    "leatherworking": "Кожевничество",
    "jewelcrafting": "Ювелирное дело",
    "alchemy": "Алхимия",
    "enchanting": "Зачарование",
}

ITEM_VALUE_TRANSLATIONS = {
    "weapon": "Оружие",
    "armor": "Броня",
    "jewelry": "Бижутерия",
    "accessory": "Аксессуар",
    "consumable": "Расходники",
    "consumables": "Расходники",
    "potion": "Расходники",
    "potion_item": "Расходники",
    "combat_item": "Расходники",
    "battle_item": "Расходники",
    "single_use": "Расходники",
    "one_time": "Расходники",
    "material": "Материалы",
    "materials": "Материалы",
    "crafting_material": "Материалы",
    "Материал": "Материалы",
    "материал": "Материалы",
    "материалы": "Материалы",
    "food": "Расходники",
    "drink": "Расходники",
    "camp_food": "Расходники",
    "resource": "Ресурс",
    "resources": "Ресурсы",
    "location_resource": "Ресурсы",
    "gathered_resource": "Ресурсы",
    "glass_gem": "драг. камень",
    "gem_imitation": "драг. камень",
    "loot": "Добыча",
    "mob_loot": "Добыча",
    "drop": "Добыча",
    "staff": "Посох",
    "sword": "Меч",
    "axe": "Топор",
    "dagger": "Кинжал",
    "bow": "Лук",
    "crossbow": "Арбалет",
    "quiver": "Колчан",
    "arrow_quiver": "Колчан стрел",
    "bolt_quiver": "Колчан болтов",
    "ammunition": "Боеприпас",
    "arrow": "Стрела",
    "bolt": "Болт",
    "mace": "Булава",
    "hammer": "Молот",
    "shield": "Щит",
    "cloth_armor": "Тканевая броня",
    "light_armor": "Лёгкая броня",
    "medium_armor": "Средняя броня",
    "heavy_armor": "Тяжёлая броня",
    "light_boots": "Лёгкие сапоги",
    "cloth_headwear": "Тканевый головной убор",
    "ring": "Кольцо",
    "necklace": "Ожерелье",
    "helmet": "Шлем",
    "chest": "Нагрудник",
    "pants": "Штаны",
    "boots": "Ботинки",
    "gloves": "Перчатки",
    "belt": "Пояс",
    "special": "Особый предмет",
    "physical": "Физический",
    "magic": "Магический",
    "physical_blunt": "Дробящий физический",
    "melee": "Ближний бой",
    "ranged": "Дальний бой",
    "normal": "Обычная",
    "ingredient": "Ингредиент",
    "ore": "Руда",
    "wood": "Дерево",
    "herb": "Трава",
    "mushroom": "Гриб",
    "stone": "Камень",
    "hide": "Шкура",
    "claw": "Коготь",
    "fang": "Клык",
}

ENGLISH_ITEM_NAME_TRANSLATIONS = {
    "wooden staff": "Деревянный посох",
    "tunic": "Туника",
    "canvas pants": "Холщевые штаны",
    "old boots": "Старые сапоги",
    "bandana": "Бандана",
}


logger = logging.getLogger(__name__)


RACE_MODEL_KEYS = {
    "human": "human",
    "elf": "elf",
    "dwarf": "dwarf",
    "undead": "undead",
    "lizardfolk": "lizardfolk",
}

# Подписи базовых характеристик расы для блока «Бонусы расы» (ТЗ §8).
_RACE_STAT_LABELS = (
    ("strength", "Сила"),
    ("dexterity", "Ловкость"),
    ("endurance", "Выносливость"),
    ("intelligence", "Интеллект"),
    ("wisdom", "Мудрость"),
    ("perception", "Восприятие"),
)


def _races_catalog() -> dict[str, Any]:
    """Published registration races; legacy JSON is fallback."""
    try:
        from services.registration_service import load_races
        catalog = load_races()
        return catalog if isinstance(catalog, dict) else {}
    except Exception:
        return {}


def _profile_race_info(race_key: str) -> dict[str, Any] | None:
    """Описание/статы/бонусы расы для профиля (ТЗ §8).

    Заменяет захардкоженный список рас во фронтенде: данные берутся из
    единого data/races.json, поэтому правки рас не нужно дублировать в UI.
    """
    race = _races_catalog().get(race_key)
    if not isinstance(race, dict):
        return None
    stats = race.get("stats") or {}
    stats_text = " · ".join(
        f"{label} {stats.get(key)}" for key, label in _RACE_STAT_LABELS if stats.get(key) is not None
    )
    return {
        "key": race_key,
        "name": race.get("name", race_key),
        "description": race.get("description", ""),
        "statsText": stats_text,
        "bonuses": list(race.get("bonuses") or []),
    }


class SpendAttributeRequest(BaseModel):
    attribute_key: str
    amount: int = Field(gt=0)


class ConfirmAttributeAllocationsRequest(BaseModel):
    allocations: dict[str, int] = Field(default_factory=dict)


class SpendSkillRequest(BaseModel):
    skill_id: str
    modifier_id: str | None = None
    amount: int = Field(gt=0)


class SkillEquipRequest(BaseModel):
    skill_id: str


class SkillUseRequest(BaseModel):
    skill_id: str


class EquipItemRequest(BaseModel):
    item_id: str
    slot_key: str | None = None
    inventory_index: int | None = Field(default=None, ge=0)


class UnequipItemRequest(BaseModel):
    slot_key: str


class UseItemRequest(BaseModel):
    item_id: str
    inventory_index: int | None = Field(default=None, ge=0)


class ProfileItemActionRequest(UseItemRequest):
    action: str


class CraftOperationRequest(UseItemRequest):
    operation: str
    rule_id: str


class DropItemRequest(BaseModel):
    item_id: str
    amount: int = Field(gt=0)
    inventory_index: int | None = Field(default=None, ge=0)


class SellItemRequest(BaseModel):
    item_id: str
    amount: int = Field(gt=0)
    inventory_index: int | None = Field(default=None, ge=0)


class PromoRedeemRequest(BaseModel):
    code: str


class EditProfileFieldRequest(BaseModel):
    field: str
    value: str


class RaceChangePreviewRequest(BaseModel):
    target_race_id: str
    method: str = "service"


class RaceChangeConfirmRequest(BaseModel):
    confirmation_token: str


class CourierTransferItem(BaseModel):
    item_id: str
    inventory_index: int | None = Field(default=None, ge=0)
    amount: int = Field(gt=0)


class CourierSendRequest(BaseModel):
    receiver: str
    items: list[CourierTransferItem] = Field(default_factory=list)
    coins: int = Field(default=0, ge=0)
    letter: str = ""


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def consumable_effect_duration_seconds(item: dict[str, Any], effect_payload: dict[str, Any]) -> int:
    for key in ("duration_seconds", "duration", "effect_duration_seconds", "buff_duration_seconds"):
        value = effect_payload.get(key) if isinstance(effect_payload, dict) else None
        if value is None:
            value = item.get(key)
        seconds = safe_int(value, 0)
        if seconds > 0:
            return seconds
    # Любой расходник с баффом по умолчанию временный, чтобы бонусы не копились навсегда.
    return 3600


def consumable_effect_stack_rule(item: dict[str, Any], effect_payload: dict[str, Any]) -> str:
    raw = effect_payload.get("stack_rule") if isinstance(effect_payload, dict) else None
    raw = raw or item.get("stack_rule") or item.get("effect_stack_rule") or "refresh"
    rule = str(raw).casefold()
    if rule in {"replace", "refresh", "stack_to_limit"}:
        return rule
    return "refresh"


def inventory_pocket_spec(item: dict[str, Any]) -> dict[str, int] | None:
    """Read an inventory-pocket consumable spec: per-use bonus and its cap."""
    payload = item.get("use_effect") if isinstance(item.get("use_effect"), dict) else item
    if not isinstance(payload, dict):
        return None
    per_use = safe_int(payload.get("pocket_bonus_per_use"), 0)
    cap = safe_int(payload.get("pocket_cap"), 0)
    if per_use <= 0 or cap <= 0:
        return None
    return {"per_use": per_use, "cap": cap}


def apply_inventory_pocket(player: dict[str, Any], item: dict[str, Any]) -> tuple[bool, str]:
    """Apply a permanent inventory expansion from a pocket, respecting its cap."""
    spec = inventory_pocket_spec(item)
    if not spec:
        return False, "Этот предмет не расширяет инвентарь."
    current = max(0, safe_int(player.get("inventory_pocket_bonus"), 0))
    if current >= spec["cap"]:
        return False, f"Этим типом кармана инвентарь уже расширен до предела (+{spec['cap']} слотов). Нужен карман более высокого уровня."
    gain = min(spec["per_use"], spec["cap"] - current)
    player["inventory_pocket_bonus"] = current + gain
    return True, f"Инвентарь расширен на +{gain} слот. Всего от карманов: +{current + gain}."


def resource_max_percent_from_item(item: dict[str, Any]) -> dict[str, int] | None:
    """Read a resource_max_percent payload (mana/spirit/life crystals)."""
    payload = item.get("use_effect") if isinstance(item.get("use_effect"), dict) else item
    raw = payload.get("resource_max_percent") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        return None
    percents: dict[str, int] = {}
    for key in ("max_hp", "max_spirit", "max_mana"):
        value = safe_int(raw.get(key), 0)
        if value:
            percents[key] = value
    return percents or None


def resource_crystal_effect_from_item(item: dict[str, Any]) -> dict[str, Any] | None:
    """Build a temporary active effect for a resource crystal consumable."""
    percents = resource_max_percent_from_item(item)
    if not percents:
        return None
    payload = item.get("use_effect") if isinstance(item.get("use_effect"), dict) else {}
    duration_seconds = safe_int(payload.get("duration_seconds") or item.get("duration_seconds"), 3600)
    if duration_seconds <= 0:
        duration_seconds = 3600
    now = datetime.now(timezone.utc)
    item_id = str(item.get("id") or item.get("item_id") or item.get("name") or "crystal")
    return {
        "id": f"effect_{item_id}",
        "name": item.get("effect_name") or payload.get("name") or item.get("name") or "Кристалл",
        "source": "resource_crystal",
        "resource_max_percent": percents,
        "duration_seconds": duration_seconds,
        "expires_at": (now + timedelta(seconds=duration_seconds)).isoformat(),
        "stack_rule": "refresh",
        "description": item.get("effect_description") or payload.get("description") or item.get("description") or "Временное изменение максимума ресурсов.",
    }


GENDER_OPTIONS = {"male": "Муж.", "female": "Жен."}
PROFILE_EDITABLE_FIELDS = ("name", "race", "gender")


def gender_label_ru(gender_id: Any, fallback: Any = None) -> str:
    gid = str(gender_id or "").strip().casefold()
    if gid in GENDER_OPTIONS:
        return GENDER_OPTIONS[gid]
    text = str(fallback or "").strip()
    return text or "Не выбран"


def profile_field_edit_availability(player: dict[str, Any]) -> dict[str, bool]:
    """True для поля = осталась 1 бесплатная попытка изменить его в сводке."""
    used = player.get("profile_field_edits")
    used = used if isinstance(used, dict) else {}
    return {field: safe_int(used.get(field), 0) < 1 for field in PROFILE_EDITABLE_FIELDS}


def apply_profile_field_edit(player: dict[str, Any], field: str, value: str, storage: Any = None) -> str:
    """Тратит единственную бесплатную попытку и меняет имя/расу/пол в сводке.

    Возвращает новое отображаемое значение. Бросает HTTPException, если поле
    неизвестно, попытки исчерпаны или значение некорректно.
    """
    field = str(field or "").strip().casefold()
    if field not in PROFILE_EDITABLE_FIELDS:
        raise HTTPException(status_code=400, detail="Это поле нельзя изменить.")
    edits = player.get("profile_field_edits")
    if not isinstance(edits, dict):
        player["profile_field_edits"] = edits = {}
    if safe_int(edits.get(field), 0) >= 1:
        raise HTTPException(status_code=409, detail="У вас закончились попытки изменить это поле.")

    raw = str(value or "").strip()
    if field == "name":
        # Те же правила, что и при регистрации: длина, допустимые символы,
        # запрещённые имена, нормализация — плюс проверка занятости.
        from services.registration_service import validate_name

        ok, result = validate_name(raw)
        if not ok:
            raise HTTPException(status_code=400, detail=result)
        name = result
        current = str(player.get("name") or "")
        if name.casefold() != current.casefold():
            is_taken = getattr(storage, "is_name_taken", None)
            if callable(is_taken) and is_taken(name):
                raise HTTPException(status_code=409, detail="Это имя уже занято.")
        player["name"] = name
        label = name
    elif field == "gender":
        folded = raw.casefold()
        chosen = folded if folded in GENDER_OPTIONS else {"муж.": "male", "муж": "male", "жен.": "female", "жен": "female"}.get(folded)
        if chosen not in GENDER_OPTIONS:
            raise HTTPException(status_code=400, detail="Выберите пол: Муж. или Жен.")
        player["gender"] = chosen
        player["gender_label"] = GENDER_OPTIONS[chosen]
        label = GENDER_OPTIONS[chosen]
    else:  # race
        from services.registration_service import load_races
        races = load_races("data/races.json")
        race_id = raw if raw in races else next((key for key, data in races.items() if str(data.get("name", "")).casefold() == raw.casefold()), None)
        if not race_id or race_id not in races:
            raise HTTPException(status_code=400, detail="Неизвестная раса.")
        race = races[race_id]
        player["race_id"] = race_id
        player["race_name"] = race.get("name", race_id)
        # Базовые статы расы статичны (вложенные/бонусные очки отдельно) — безопасно заменить.
        player["stats"] = dict(race.get("stats") or {})
        label = race.get("name", race_id)

    edits[field] = safe_int(edits.get(field), 0) + 1
    return label


SUSPICIOUS_POTION_ATTRS = {
    "bonus_strength": "Сила",
    "bonus_agility": "Ловкость",
    "bonus_endurance": "Выносливость",
    "bonus_intelligence": "Интеллект",
    "bonus_wisdom": "Мудрость",
    "bonus_perception": "Восприятие",
}


def is_suspicious_potion_item(item: dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    if bool(item.get("random_attribute_potion")):
        return True
    return str(item.get("item_id") or item.get("id") or "").strip() == "suspicious_potion"


def suspicious_potion_effect(player: dict[str, Any], rng=None) -> dict[str, Any]:
    """Случайный баф/дебаф подозрительного зелья (1–3 характеристики, 30 минут).

    50/50 усиление либо ослабление; число затронутых характеристик 1–3; величина
    каждого изменения 1..макс, где макс растёт с уровнем игрока.
    """
    import random as _random

    rng = rng or _random.Random()
    level = max(1, safe_int(player.get("level"), 1))
    max_magnitude = max(1, level // 5 + 1)
    sign = 1 if rng.random() < 0.5 else -1
    count = rng.randint(1, 3)
    keys = list(SUSPICIOUS_POTION_ATTRS)
    chosen = rng.sample(keys, count)
    modifiers = {key: sign * rng.randint(1, max_magnitude) for key in chosen}
    now = datetime.now(timezone.utc)
    kind = "усиление" if sign > 0 else "ослабление"
    parts = [f"{SUSPICIOUS_POTION_ATTRS[key]} {'+' if value > 0 else ''}{value}" for key, value in modifiers.items()]
    summary = ", ".join(parts)
    return {
        "id": "effect_suspicious_potion",
        "name": f"Подозрительное зелье ({kind})",
        "source": "consumable",
        "kind": "positive" if sign > 0 else "negative",
        "stat_modifiers": modifiers,
        "duration_seconds": 1800,
        "expires_at": (now + timedelta(seconds=1800)).isoformat(),
        "stack_rule": "refresh",
        "description": f"Случайный эффект подозрительного зелья на 30 минут: {summary}.",
        "message": f"Подозрительное зелье даёт {kind}: {summary} (30 минут).",
    }


def consumable_effect_from_item(item: dict[str, Any]) -> dict[str, Any] | None:
    effect_payload = item.get("use_effect") or item.get("active_effect") or item.get("consumable_effect")
    if effect_payload is None and any(field in item for field in ("stat_modifiers", "modifiers", "bonus_modifiers", "effect_modifiers", "bonuses")):
        effect_payload = item
    if effect_payload is None:
        return None
    if not isinstance(effect_payload, dict):
        effect_payload = {}
    totals: dict[str, int] = {}
    collect_modifiers_from_value(effect_payload, totals)
    if not totals:
        return None
    duration_seconds = consumable_effect_duration_seconds(item, effect_payload)
    now = datetime.now(timezone.utc)
    return {
        "id": f"effect_{item.get('id') or item.get('item_id') or item.get('name')}",
        "name": item.get("effect_name") or effect_payload.get("name") or item.get("name") or "Временный эффект",
        "source": "consumable",
        "stat_modifiers": totals,
        "duration_seconds": duration_seconds,
        "expires_at": (now + timedelta(seconds=duration_seconds)).isoformat(),
        "stack_rule": consumable_effect_stack_rule(item, effect_payload),
        "max_stacks": max(1, safe_int(effect_payload.get("max_stacks") or item.get("max_stacks"), 1)),
        "description": item.get("effect_description") or effect_payload.get("description") or item.get("description") or "Временный эффект от использованного предмета.",
    }


def add_active_consumable_effect(player: dict[str, Any], effect: dict[str, Any]) -> None:
    effects = player.setdefault("active_effects", [])
    if not isinstance(effects, list):
        player["active_effects"] = effects = []
    prune_expired_effects(player)
    effect_id = str(effect.get("id") or "")
    rule = str(effect.get("stack_rule") or "refresh").casefold()
    same_indexes = [index for index, active in enumerate(effects) if isinstance(active, dict) and str(active.get("id") or "") == effect_id]

    if rule in {"replace", "refresh"}:
        for index in reversed(same_indexes):
            effects.pop(index)
        effects.append(effect)
        return

    if rule == "stack_to_limit":
        max_stacks = max(1, safe_int(effect.get("max_stacks"), 1))
        if len(same_indexes) >= max_stacks:
            effects.pop(same_indexes[0])
        effects.append(effect)
        return

    effects.append(effect)


def item_energy_restore(item: dict[str, Any]) -> int:
    """Return ready energy restore amount from food, drinks or consumables."""
    effect_payload = item.get("use_effect") or item.get("active_effect") or item.get("consumable_effect") or {}
    if not isinstance(effect_payload, dict):
        effect_payload = {}
    for key in (
        "energy_restore",
        "restore_energy",
        "energyRestored",
        "energy_restore_amount",
        "base_energy_restore",
        "energy",
    ):
        value = item.get(key)
        if value is None:
            value = effect_payload.get(key)
        amount = safe_int(value, 0)
        if amount > 0:
            return amount
    return 0



BATTLE_STIMULANT_ITEM_IDS = {"battle_stimulant"}


def is_battle_stimulant_item(item: dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    item_id = str(item.get("item_id") or item.get("id") or "").strip()
    return item_id in BATTLE_STIMULANT_ITEM_IDS


def battle_stimulant_effect_from_item(item: dict[str, Any]) -> dict[str, Any]:
    payload = item.get("use_effect") if isinstance(item.get("use_effect"), dict) else None
    if payload is None:
        payload = item.get("combat_effect") if isinstance(item.get("combat_effect"), dict) else {}
    damage_bonus = safe_int(payload.get("damage_bonus_percent"), 30)
    resource_bonus = safe_int(payload.get("resource_max_bonus_percent"), 20)
    duration_seconds = safe_int(payload.get("duration_seconds") or item.get("duration_seconds"), 1800)
    if duration_seconds <= 0:
        duration_seconds = 1800
    now = datetime.now(timezone.utc)
    return {
        "id": "effect_battle_stimulant",
        "name": item.get("effect_name") or item.get("name") or "Боевой стимулятор",
        "source": "battle_stimulant",
        "source_item_id": "battle_stimulant",
        "duration_seconds": duration_seconds,
        "expires_at": (now + timedelta(seconds=duration_seconds)).isoformat(),
        "stack_rule": "refresh",
        "combat_damage_bonus_percent": damage_bonus,
        "resource_max_bonus_percent": resource_bonus,
        "description": item.get("effect_description") or "Боевой стимулятор принят из инвентаря: урон навыков +30%, максимум Духа и Маны +20% на 30 минут.",
    }


def apply_battle_stimulant_inventory_effect(player: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    """Apply the battle stimulant from inventory, not from the combat pouch."""

    from services.battle_stimulant_service import register_battle_stimulant_use

    effect = battle_stimulant_effect_from_item(item)
    effects = player.setdefault("active_effects", [])
    if not isinstance(effects, list):
        effects = []
        player["active_effects"] = effects
    prune_expired_effects(player)
    effect_id = str(effect.get("id") or "effect_battle_stimulant")
    for index in range(len(effects) - 1, -1, -1):
        active = effects[index]
        if isinstance(active, dict) and str(active.get("id") or "") == effect_id:
            effects.pop(index)
    effects.append(effect)
    # Re-use refreshes the active duration, schedules the 2h withdrawal and grows
    # the permanent "Зависимость" stack. While active, addiction stays blocked.
    register_battle_stimulant_use(player)
    return effect


def _battle_stimulant_status_effects(player: dict[str, Any]) -> list[dict[str, Any]]:
    """Withdrawal / addiction cards for the profile effects list."""

    from services.battle_stimulant_service import battle_stimulant_status_effect

    status = battle_stimulant_status_effect(player)
    return [status] if status else []

def apply_energy_restore(player: dict[str, Any], item: dict[str, Any]) -> int:
    restore = item_energy_restore(item)
    if restore <= 0:
        return 0
    # Use the unified derived stats service so expired effects are pruned and
    # do not affect food/energy restoration.
    derived = calculate_player_derived_stats(player)
    bonus_modifiers = derived.get("bonus_modifiers", {})
    energy_stats = calculate_energy_stats(player, bonus_modifiers)
    max_energy = energy_stats["max_energy"]
    current = energy_stats["current_energy"]
    bonus_percent = max(0, safe_int(player.get("bonus_energy_restore_percent"), 0) + equipment_bonus(bonus_modifiers, "bonus_energy_restore_percent"))
    final_restore = ceil(restore * (1 + bonus_percent / 100))
    new_value = min(max_energy, current + final_restore)
    player.setdefault("base_max_energy", energy_stats["base_max_energy"])
    player["energy"] = new_value
    player["current_energy"] = new_value
    if new_value > 50:
        player.pop("energy_warning_50_sent", None)
    if new_value > 10:
        player.pop("energy_warning_10_sent", None)
    return new_value - current



from services.currency import format_money, format_price  # noqa: E402  (shared denomination formatter)
from services.courier_service import (  # noqa: E402
    LETTER_MAX_LENGTH as COURIER_LETTER_MAX_LENGTH,
    CourierError,
    create_courier_transfer,
    delivery_cost_copper as courier_delivery_cost_copper,
    courier_warning_text,
    search_players as courier_search_players,
)


def format_date(raw_value: str | None) -> str:
    if not raw_value:
        return "—"
    try:
        value = datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
        return value.strftime("%d.%m.%Y")
    except ValueError:
        return str(raw_value)


def normalize_quality(value: str | None) -> str:
    return (value or "обычный").strip().lower()


def translate_item_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    translated = ITEM_VALUE_TRANSLATIONS.get(stripped.casefold())
    return translated or stripped


def translate_item_name(value: Any) -> str:
    if not isinstance(value, str):
        return "Безымянный предмет"
    stripped = value.strip()
    return ENGLISH_ITEM_NAME_TRANSLATIONS.get(stripped.casefold(), stripped or "Безымянный предмет")


HIDDEN_FORMULA_KEYS = {"formula", "base_damage_formula", "damage_formula", "scaling_formula"}
FORMULA_TEXT_MARKERS = ("player_level", "ceil(", "floor(", "log2(", "ln(", "уровень ×", "уровня ×", "уровень персонажа ×")
CONCENTRATION_TEXT_MARKERS = ("концентрац", "concentration")
STAT_EQUIPMENT_BONUS_KEYS = {
    "strength": "bonus_strength",
    "endurance": "bonus_endurance",
    "dexterity": "bonus_agility",
    "perception": "bonus_perception",
    "intelligence": "bonus_intelligence",
    "wisdom": "bonus_wisdom",
}
ITEM_STAT_LABEL_TO_MODIFIER = {
    "броня": "armor",
    "магическая броня": "magic_armor",
    "маг. броня": "magic_armor",
    "магическая защита": "bonus_magic_defense",
    "физическая защита": "bonus_physical_defense",
    "hp": "bonus_hp",
    "здоровье": "bonus_hp",
    "дух": "bonus_spirit",
    "мана": "bonus_mana",
    "точность": "bonus_accuracy",
    "уклонение": "bonus_dodge",
    "шанс крита": "bonus_crit_chance",
    "урон крита": "bonus_crit_damage",
    "критический урон": "bonus_crit_damage",
    "реген hp": "bonus_hp_regen_percent",
    "регенерация hp": "bonus_hp_regen_percent",
    "реген здоровья": "bonus_hp_regen_percent",
    "реген духа": "bonus_spirit_regen_percent",
    "регенерация духа": "bonus_spirit_regen_percent",
    "реген маны": "bonus_mana_regen_percent",
    "регенерация маны": "bonus_mana_regen_percent",
    "энергия": "bonus_max_energy",
    "макс. энергия": "bonus_max_energy",
    "максимальная энергия": "bonus_max_energy",
    "экономия энергии": "bonus_energy_saving_percent",
    "восстановление энергии": "bonus_energy_restore_percent",
    "урон": "bonus_damage",
    "физический урон": "bonus_physical_damage",
    "магический урон": "bonus_magic_damage",
    "сила": "bonus_strength",
    "выносливость": "bonus_endurance",
    "ловкость": "bonus_agility",
    "восприятие": "bonus_perception",
    "интеллект": "bonus_intelligence",
    "мудрость": "bonus_wisdom",
}
MODIFIER_KEY_ALIASES = {
    "hp": "bonus_hp",
    "spirit": "bonus_spirit",
    "mana": "bonus_mana",
    "strength": "bonus_strength",
    "endurance": "bonus_endurance",
    "agility": "bonus_agility",
    "dexterity": "bonus_agility",
    "perception": "bonus_perception",
    "intelligence": "bonus_intelligence",
    "wisdom": "bonus_wisdom",
    "crit_damage_percent": "bonus_crit_damage",
    "bonus_crit_damage_percent": "bonus_crit_damage",
    "critical_damage": "bonus_crit_damage",
    "critical_damage_percent": "bonus_crit_damage",
    "hp_regen_percent": "bonus_hp_regen_percent",
    "spirit_regen_percent": "bonus_spirit_regen_percent",
    "mana_regen_percent": "bonus_mana_regen_percent",
    "max_energy": "bonus_max_energy",
    "energy_saving_percent": "bonus_energy_saving_percent",
    "energy_restore_bonus_percent": "bonus_energy_restore_percent",
    "energy_restore_percent": "bonus_energy_restore_percent",
    "physical_damage": "bonus_physical_damage",
    "magic_damage": "bonus_magic_damage",
    "damage": "bonus_damage",
}
KNOWN_MODIFIER_KEYS = {
    "armor",
    "magic_armor",
    "bonus_hp",
    "bonus_spirit",
    "bonus_mana",
    "bonus_physical_defense",
    "bonus_magic_defense",
    "bonus_accuracy",
    "bonus_dodge",
    "bonus_crit_chance",
    "bonus_crit_damage",
    "bonus_strength",
    "bonus_endurance",
    "bonus_agility",
    "bonus_perception",
    "bonus_intelligence",
    "bonus_wisdom",
    "bonus_hp_regen_percent",
    "bonus_spirit_regen_percent",
    "bonus_mana_regen_percent",
    "bonus_max_energy",
    "bonus_energy_saving_percent",
    "bonus_energy_restore_percent",
    "bonus_damage",
    "bonus_physical_damage",
    "bonus_magic_damage",
}
EXTERNAL_EFFECT_FIELDS = (
    "active_effects",
    "effects",
    "temporary_effects",
    "location_effects",
    "active_location_effects",
    "environment_effects",
    "active_buffs",
    "buffs",
    "potions",
    "consumed_potions",
    "active_consumables",
    "active_food_effects",
    "active_sets",
)


def contains_formula_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.casefold()
    return any(marker in lowered for marker in FORMULA_TEXT_MARKERS)


def contains_concentration_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.casefold()
    return any(marker in lowered for marker in CONCENTRATION_TEXT_MARKERS)


def strip_hidden_formulas(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, nested_value in value.items():
            key_text = str(key).casefold()
            if key_text in HIDDEN_FORMULA_KEYS or "formula" in key_text:
                continue
            cleaned_value = strip_hidden_formulas(nested_value)
            if cleaned_value is None:
                continue
            cleaned[key] = cleaned_value
        return cleaned
    if isinstance(value, list):
        return [cleaned for item in value if (cleaned := strip_hidden_formulas(item)) is not None]
    if contains_formula_text(value):
        return None
    return value



CONSUMABLE_CATEGORY_MARKERS = {
    "еда", "напитки", "напиток", "зелье", "зелья", "расходник", "расходники",
    "consumable", "consumables", "potion", "food", "drink", "camp_food", "combat_item",
    "battle_item", "single_use", "one_time", "одноразовый", "боевой предмет",
    "ammunition", "ammo", "arrow", "bolt", "боеприпас", "боеприпасы", "стрела", "стрелы", "болт", "болты",
}
RESOURCE_TYPE_MARKERS = {
    "ore", "wood", "tree", "herb", "flower", "mushroom", "stone", "resource", "resources",
    "руда", "дерево", "древесина", "трава", "травы", "цветок", "цветы", "гриб", "грибы",
    "камень", "камни", "корень", "корни", "ягода", "ягоды", "ингредиент", "ингредиенты",
}
MATERIAL_TYPE_MARKERS = {
    "material", "materials", "crafting_material", "craft_material", "crafting",
    "glass_gem", "gem_imitation", "драг. камень", "драгоценный камень", "стекляшки",
    "ingot", "bar", "scrap", "cloth", "fabric", "leather", "hide", "plank", "board",
    "материал", "материалы", "ремесленный материал", "крафт", "слиток", "слитки",
    "лом", "ткань", "кожа", "шкура", "доска", "доски", "полоски кожи",
}
MOB_LOOT_MARKERS = ("моб", "добыч", "pve", "enemy", "monster", "mob")
STARTING_LOCATION_SOURCE_MARKERS = ("hilly_meadows", "ordinary_forest", "холмист", "обыкновенный лес")


def _text_parts_for_category(item: dict[str, Any]) -> set[str]:
    parts = {
        str(item.get("category") or "").casefold(),
        str(item.get("type") or "").casefold(),
        str(item.get("subtype") or "").casefold(),
        str(item.get("item_class") or "").casefold(),
    }
    tags = item.get("integration_tags") or item.get("tags") or []
    if isinstance(tags, list):
        parts.update(str(tag).casefold() for tag in tags)
    return {part for part in parts if part}


ORE_TYPE_MARKERS = {"ore", "руда", "руды"}
GLASS_GEM_MARKERS = {"glass_gem", "gem_imitation", "драг. камень", "драгоценный камень", "стекляшки"}


def is_ore_resource_item(item: dict[str, Any]) -> bool:
    parts = _text_parts_for_category(item)
    name = str(item.get("name") or item.get("name_ru") or "").casefold()
    return bool(parts & ORE_TYPE_MARKERS) or "руд" in name


def is_glass_gem_item(item: dict[str, Any]) -> bool:
    parts = _text_parts_for_category(item)
    name = str(item.get("name") or item.get("name_ru") or "").casefold()
    item_id = str(item.get("id") or item.get("item_id") or "").casefold()
    return bool(parts & GLASS_GEM_MARKERS) or "стекляш" in name or item_id.startswith("glass_")


def classify_profile_inventory_category(item: dict[str, Any], current_category: str) -> str:
    source_text = str(item.get("source") or item.get("origin") or "").casefold()
    parts = _text_parts_for_category(item)
    if any(marker in source_text for marker in MOB_LOOT_MARKERS) or current_category in {"Добыча", "Трофеи"}:
        return "Добыча"
    equipment_markers = {"equipment", "экипировка", "снаряжение", "weapon", "оружие", "armor", "броня", "jewelry", "бижутерия"}
    if parts & equipment_markers:
        return current_category
    if any(marker in source_text for marker in STARTING_LOCATION_SOURCE_MARKERS) or parts & {"hilly_meadows", "ordinary_forest"}:
        return "Ресурсы"
    if item_energy_restore(item) > 0 or parts & CONSUMABLE_CATEGORY_MARKERS:
        return "Расходники"
    if is_glass_gem_item(item):
        return "Материалы"
    # Руда — это ресурс, даже если у неё есть ремесленные теги.
    if is_ore_resource_item(item):
        return "Ресурсы"
    if current_category in {"Материал", "Материалы"} or parts & MATERIAL_TYPE_MARKERS:
        return "Материалы"
    if current_category in {"Ресурс", "Ресурсы", "Ингредиенты"} or parts & RESOURCE_TYPE_MARKERS:
        return "Ресурсы"
    return current_category


def is_profile_material_item(item: dict[str, Any]) -> bool:
    category = str(item.get("category") or "").casefold()
    parts = _text_parts_for_category(item)
    return is_glass_gem_item(item) or category in {"материал", "материалы"} or bool(parts & MATERIAL_TYPE_MARKERS)


DIRECTLY_USABLE_CATEGORY_MARKERS = {
    "еда", "напитки", "напиток", "зелье", "зелья",
    "potion", "food", "drink", "camp_food",
}
EQUIPMENT_CATEGORY_MARKERS = {
    "equipment", "экипировка", "снаряжение",
}
EQUIPMENT_SLOT_KEYS = {
    "helmet", "necklace", "chest", "belt", "pants", "boots", "gloves",
    "ring", "ring1", "ring2", "weapon", "weapon1", "weapon2",
    "main_hand", "off_hand", "special",
}


def is_profile_equipment_item(item: dict[str, Any]) -> bool:
    parts = _text_parts_for_category(item)
    raw_slot = str(item.get("targetSlotKey") or item.get("slotKey") or item.get("slot") or item.get("target_slot") or "").casefold().strip()
    return raw_slot in EQUIPMENT_SLOT_KEYS or bool(parts & EQUIPMENT_CATEGORY_MARKERS)


def is_direct_profile_use_disabled(item: dict[str, Any]) -> bool:
    false_values = {"0", "false", "no", "off", "disabled", "нет", "нельзя"}
    for key in ("direct_use", "directUse", "profile_use", "profileUse", "profile_usable", "profileUsable", "can_use", "canUse", "usable"):
        if key not in item:
            continue
        value = item.get(key)
        if isinstance(value, bool):
            return value is False
        if isinstance(value, (int, float)):
            return value == 0
        if str(value).strip().casefold() in false_values:
            return True
    return False


def has_explicit_consumable_effect(item: dict[str, Any]) -> bool:
    if not any(item.get(field) is not None for field in ("use_effect", "active_effect", "consumable_effect")):
        return False
    return consumable_effect_from_item(item) is not None


def is_inventory_item_usable(item: dict[str, Any]) -> bool:
    category = str(item.get("category") or "").casefold()
    parts = _text_parts_for_category(item)
    usable_markers = CONSUMABLE_CATEGORY_MARKERS | DIRECTLY_USABLE_CATEGORY_MARKERS
    if is_profile_equipment_item(item):
        return False
    if is_direct_profile_use_disabled(item):
        return False
    return bool(item.get("can_open") or item.get("grants_npc_helper_id") or (item.get("opens_access") and str(item.get("access_mode") or "on_use")=="on_use")) or is_ammunition_item(item) or item_energy_restore(item) > 0 or has_explicit_consumable_effect(item) or resource_max_percent_from_item(item) is not None or inventory_pocket_spec(item) is not None or category == "расходники" or bool(parts & usable_markers)

def normalize_item(item: dict[str, Any], default_category: str = "Прочее") -> dict[str, Any]:
    item = enrich_inventory_item(item)
    normalized = strip_hidden_formulas(deepcopy(item))
    if not isinstance(normalized, dict):
        normalized = {}
    normalized.setdefault("id", normalized.get("item_id") or normalized.get("name") or "item")
    normalized["name"] = translate_item_name(normalized.get("name"))
    normalized["category"] = translate_item_value(normalized.get("category") or default_category)
    normalized["category"] = classify_profile_inventory_category(normalized, str(normalized.get("category") or "Прочее"))
    raw_subtype = normalized.get("subtype")
    raw_type = normalized.get("type") or normalized.get("slotKey") or normalized.get("slot") or "Предмет"
    translated_subtype = translate_item_value(raw_subtype) if raw_subtype else None
    translated_type = translate_item_value(raw_type)
    normalized["type"] = translated_subtype if translated_subtype and translated_type in {"Оружие", "Броня", "Предмет"} else translated_type
    if raw_subtype:
        normalized["subtype"] = translated_subtype
    normalized["quality"] = normalize_quality(normalized.get("quality"))
    if is_levelled_equipment_item(normalized):
        normalized["level"] = max(1, safe_int(normalized.get("level"), 1))
        normalized["required_level"] = max(1, safe_int(normalized.get("required_level"), normalized["level"]))
    else:
        normalized.pop("level", None)
        normalized.pop("required_level", None)
    normalized.setdefault("description", "Описание предмета пока не добавлено.")
    normalized.setdefault("stats", [])
    normalized.setdefault("enchantments", [])
    normalized.setdefault("compare", [])
    normalized.setdefault("amount", 1)

    raw_sell_price = normalized.get("sell_price_copper", normalized.get("sellPriceCopper"))
    sell_price = safe_int(raw_sell_price, -1)
    raw_can_sell = normalized.get("can_sell", normalized.get("canSell"))
    can_sell = bool(raw_can_sell) if raw_can_sell is not None else sell_price >= 0
    normalized["can_sell"] = can_sell
    normalized["canSell"] = can_sell
    if sell_price >= 0:
        normalized["sell_price_copper"] = sell_price
        normalized["sellPriceCopper"] = sell_price
        normalized["sellPriceText"] = format_price(sell_price)
    elif can_sell is False:
        normalized["sellPriceText"] = "не продаётся"

    if normalized.get("overflow_slot"):
        normalized["overflowSlot"] = True
        normalized["inventoryStatus"] = "Перегруз"
    energy_restore = item_energy_restore(normalized)
    stats = list(normalized.get("stats") or [])
    if energy_restore > 0:
        normalized["category"] = "Расходники"
        if not any("энерг" in str(line).casefold() for line in stats):
            stats.append(f"Восстановление энергии: +{energy_restore}")
    if safe_int(normalized.get("capacity"), 0) > 0 and ("quiver" in str(normalized.get("subtype") or "").casefold() or "колчан" in str(normalized.get("type") or "").casefold()):
        ammo_count = safe_int(normalized.get("ammo_count"), 0)
        capacity = safe_int(normalized.get("capacity"), 0)
        ammo_line = f"Заряжено: {ammo_count}/{capacity}"
        # Старые сохранения могли хранить строку "Заряжено: 0/30" прямо в stats.
        # Если её не удалить, профиль продолжит показывать 0 даже после загрузки стрел/болтов.
        stats = [line for line in stats if "заряжено" not in str(line).casefold()]
        stats.append(ammo_line)
    normalized["stats"] = stats
    normalized["isMaterial"] = is_profile_material_item(normalized)
    return normalized


def format_skill_damage(
    skill: dict[str, Any],
    player_level: int,
    bonus_modifiers: dict[str, int] | None = None,
    player: dict[str, Any] | None = None,
) -> Any:
    if not isinstance(skill, dict):
        return None
    if player is not None:
        result = calculate_player_skill_raw_damage(player, skill)
        return result.get("damage")
    damage = skill.get("damage")
    if contains_formula_text(damage):
        return None
    if isinstance(damage, (int, float)):
        return max(1, ceil(float(damage) + equipment_bonus(bonus_modifiers, "bonus_damage")))
    return damage


def skill_resource_text(skill: dict[str, Any], player: dict[str, Any] | None = None) -> str:
    try:
        spirit_i, mana_i = resource_cost_with_modifiers(skill, player)
        mana = safe_float(mana_i, 0)
        spirit = safe_float(spirit_i, 0)
    except Exception:
        logger.exception("Failed to calculate profile skill resource text for skill=%r", skill.get("id") or skill.get("name"))
        mana = safe_float(skill.get("mana_cost") if "mana_cost" in skill else skill.get("manaCost"), 0)
        spirit = safe_float(skill.get("spirit_cost") if "spirit_cost" in skill else skill.get("spiritCost"), 0)
    parts: list[str] = []
    if mana > 0:
        parts.append(f"Мана: {mana:g}")
    if spirit > 0:
        parts.append(f"Дух: {spirit:g}")
    if parts:
        return "Расход: " + " · ".join(parts)
    return "Расход: не требует маны и духа"


def skill_cooldown_text(skill: dict[str, Any]) -> str:
    turns = safe_int(skill.get("cooldown_turns") if "cooldown_turns" in skill else skill.get("cooldown"), 0)
    return f"Откат: {turns} ходов"


def normalize_skill(
    skill: dict[str, Any],
    player_level: int,
    bonus_modifiers: dict[str, int] | None = None,
    source_section: str = "active",
    player: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = strip_hidden_formulas(deepcopy(skill))
    if not isinstance(normalized, dict):
        normalized = {}
    for hidden_key in ("concentration_cost", "concentrationCost", "bonus_max_concentration", "bonus_concentration_regen"):
        normalized.pop(hidden_key, None)
    damage = format_skill_damage(skill, player_level, bonus_modifiers, player)
    if damage is not None:
        normalized["damage"] = damage
    else:
        normalized.pop("damage", None)
    raw_resource_text = skill.get("resource_text") or skill.get("cost")
    if isinstance(raw_resource_text, str) and not contains_concentration_text(raw_resource_text) and not contains_formula_text(raw_resource_text):
        normalized["resourceText"] = raw_resource_text
    else:
        normalized["resourceText"] = skill_resource_text(skill, player)
    normalized["cooldownText"] = skill.get("cooldown_text") or skill_cooldown_text(skill)
    normalized["cooldown"] = safe_int(skill.get("cooldown_turns") if "cooldown_turns" in skill else skill.get("cooldown"), 0)
    normalized["level"] = skill_level(skill)
    skill_type = str(skill.get("skill_type") or skill.get("type") or source_section or "active").lower()
    normalized.setdefault("skill_type", skill_type)
    normalized["equippable"] = bool(skill.get("equippable", skill_type not in {"passive", "пассивный"}))
    # Требование к оружию показываем только для активных навыков с конкретным
    # ограничением — пассивы и «любое оружие» в подсказке не нуждаются.
    if skill_type not in {"passive", "пассивный"}:
        requirements = skill.get("weapon_requirements") or ["any"]
        if isinstance(requirements, str):
            requirements = [requirements]
        if requirements and "any" not in {str(item) for item in requirements}:
            normalized["weaponRequirementText"] = skill_weapon_requirement_text(skill)
            normalized["weaponCompatible"] = is_skill_weapon_compatible(player, skill) if player is not None else True
    return normalized


EFFECT_MODIFIER_LABELS = {
    "armor": "Броня",
    "magic_armor": "Магическая броня",
    "bonus_hp": "HP",
    "bonus_spirit": "Дух",
    "bonus_mana": "Мана",
    "bonus_physical_defense": "Физическая защита",
    "bonus_magic_defense": "Магическая защита",
    "bonus_accuracy": "Точность",
    "bonus_dodge": "Уклонение",
    "bonus_crit_chance": "Шанс крита",
    "bonus_crit_damage": "Урон крита",
    "bonus_strength": "Сила",
    "bonus_endurance": "Выносливость",
    "bonus_agility": "Ловкость",
    "bonus_perception": "Восприятие",
    "bonus_intelligence": "Интеллект",
    "bonus_wisdom": "Мудрость",
    "bonus_hp_regen_percent": "Регенерация HP",
    "bonus_spirit_regen_percent": "Регенерация духа",
    "bonus_mana_regen_percent": "Регенерация маны",
    "bonus_max_energy": "Максимальная энергия",
    "bonus_energy_saving_percent": "Экономия энергии",
    "bonus_energy_restore_percent": "Восстановление энергии",
    "bonus_damage": "Урон",
    "bonus_physical_damage": "Физический урон",
    "bonus_magic_damage": "Магический урон",
    "bonus_inventory_slots": "Слоты инвентаря",
    "bonus_stun_resist_chance": "Сопротивление оглушению",
    "bonus_blind_resist_chance": "Сопротивление ослеплению",
    "bonus_bleed_resist_chance": "Сопротивление кровотечению",
    "bonus_poison_resist_chance": "Сопротивление отравлению",
    "bonus_npc_buy_discount_percent": "Скидка у NPC",
    "bonus_npc_sell_bonus_percent": "Надбавка при продаже NPC",
}


def normalize_effect_for_frontend(effect: Any) -> dict[str, Any] | None:
    if not isinstance(effect, dict):
        return None
    normalized = strip_hidden_formulas(deepcopy(effect))
    if not isinstance(normalized, dict):
        return None

    totals: dict[str, int] = {}
    collect_modifiers_from_value(normalized, totals)
    modifiers = [
        {
            "key": key,
            "label": EFFECT_MODIFIER_LABELS.get(key, key),
            "value": value,
            "text": f"{EFFECT_MODIFIER_LABELS.get(key, key)} {'+' if value > 0 else ''}{value}",
        }
        for key, value in sorted(totals.items())
        if safe_int(value, 0) != 0
    ]
    # Percentage modifiers to max resources (mana/spirit/life crystals).
    percent_labels = {"max_hp": "Максимум HP", "max_spirit": "Максимум духа", "max_mana": "Максимум маны"}
    resource_percent = normalized.get("resource_max_percent")
    if isinstance(resource_percent, dict):
        for key, raw in resource_percent.items():
            value = safe_int(raw, 0)
            if value == 0:
                continue
            label = percent_labels.get(str(key), str(key))
            modifiers.append({
                "key": str(key),
                "label": label,
                "value": value,
                "text": f"{label} {'+' if value > 0 else ''}{value}%",
            })
    has_negative = any(safe_int(item.get("value"), 0) < 0 for item in modifiers)
    has_positive = any(safe_int(item.get("value"), 0) > 0 for item in modifiers)
    source = str(normalized.get("source") or "").casefold()
    raw_kind = str(normalized.get("kind") or normalized.get("type") or normalized.get("effect_type") or "").casefold()
    forced_negative = source in {"inventory_overflow", "debuff", "curse", "battle_stimulant_withdrawal", "battle_stimulant_addiction"} or raw_kind in {"negative", "debuff", "curse", "penalty"}
    if forced_negative:
        kind = "negative"
    elif has_positive and has_negative:
        # Mixed consumable buffs (e.g. crystals: +max mana, -max hp) are chosen
        # trade-offs, not pure penalties.
        kind = "neutral"
    elif has_negative:
        kind = "negative"
    elif has_positive or raw_kind in {"positive", "buff", "bonus"}:
        kind = "positive"
    else:
        kind = "neutral"

    return {
        "id": normalized.get("id") or normalized.get("name") or "effect",
        "name": normalized.get("name") or "Активный эффект",
        "description": normalized.get("description") or normalized.get("text") or normalized.get("details") or "Описание эффекта пока не добавлено.",
        "source": normalized.get("source") or "",
        "kind": kind,
        "expiresAt": normalized.get("expires_at") or normalized.get("expiresAt") or "",
        "durationSeconds": safe_int(normalized.get("duration_seconds") or normalized.get("durationSeconds"), 0),
        "modifiers": modifiers,
    }


# Версия структуры профиля — позволяет фронту понимать набор блоков (ТЗ §19).
PROFILE_SCHEMA_VERSION = 2

_RATING_PLACE_META = (
    ("globalPlace", "Общий рейтинг"),
    ("levelPlace", "Уровень"),
    ("pvePlace", "PVE"),
    ("pvpPlace", "PVP"),
    ("craftPlace", "Ремесло"),
    ("wealthPlace", "Богатство"),
    ("explorePlace", "Исследование"),
    ("achievementsPlace", "Достижения"),
)


def _profile_status(player: dict[str, Any]) -> dict[str, Any]:
    """Текущее состояние персонажа (ТЗ §5) — только статус, без карты/локаций."""
    in_battle = bool(player.get("in_battle"))
    has_timer = bool(player.get("active_timer"))
    try:
        has_fine = bool(fine_entries_for_profile(player))
    except Exception:
        has_fine = False
    if in_battle:
        state, label = "in_battle", "В бою"
    elif has_timer:
        state, label = "timer", "Занят действием"
    elif has_fine:
        state, label = "fine", "Активный штраф"
    else:
        state, label = "free", "Свободен"
    restricted = has_fine and bool(player.get("movement_restricted") or player.get("forced_collection"))
    return {
        "state": state,
        "label": label,
        "canUseInventory": not in_battle,
        "canMove": not (in_battle or restricted),
        "restricted": restricted,
        "hasActiveTimer": has_timer,
        "hasActiveFine": has_fine,
        "inBattle": in_battle,
    }


def _profile_rating_places(player: dict[str, Any]) -> list[dict[str, Any]]:
    """Только личные места игрока (ТЗ §5, §17) — без полных таблиц."""
    rating = player.get("rating") if isinstance(player.get("rating"), dict) else {}
    return [{"key": key, "label": label, "place": rating.get(key, "—")} for key, label in _RATING_PLACE_META]


def _profile_services(player: dict[str, Any]) -> list[dict[str, Any]]:
    """Доступные сервисы (ТЗ §10). Пустой список → вкладка «Сервисы» скрыта."""
    services=[]
    if player.get("game_id") and not player.get("courier_disabled"):services.append({"id":"transfer","label":"Передача"})
    if not player.get("promo_disabled"):services.append({"id":"promo","label":"Промокод"})
    try:
        from services.pavilion_runtime import access_active
        if access_active(player):services.append({"id":"pavilion","label":"Торговый павильон"})
    except Exception:pass
    return services


def _profile_guild(player: dict[str, Any]) -> dict[str, Any] | None:
    """Гильдейский блок профиля (ТЗ §14). None → вкладка «Гильдии» скрыта."""
    guild = player.get("guild")
    return guild if isinstance(guild, dict) and guild else None


def _profile_reputations(player: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        from services.reputation_runtime_service import player_view
        return player_view(player)
    except Exception:
        return []


def _profile_event_campaigns(player: dict[str, Any]) -> list[dict[str, Any]]:
    states = player.get("event_campaigns") if isinstance(player.get("event_campaigns"), dict) else {}
    rows=[]
    for event_id,state in states.items():
        if not isinstance(state,dict): continue
        try:
            from services.event_campaign_service import published
            data=published(str(event_id)) or {}
        except Exception: data={}
        rows.append({"id":str(event_id),"name":data.get("player_name") or data.get("name") or str(event_id),"status":state.get("status"),"stageId":state.get("stage_id"),"points":state.get("points",0),"place":state.get("place")})
    return rows


def _achievement_event(player: dict[str, Any], event_type: str, amount: float = 1,
                       target: str = "", storage: Any = None) -> None:
    try:
        from services.achievement_engine import record_game_event
        record_game_event(player, event_type, amount, target, storage=storage)
    except Exception:
        pass
    try:
        from services.quest_runtime_service import progress,trigger_source
        progress(player,event_type,target,max(1,int(amount)))
        if event_type=="use_item":trigger_source(player,"item",target)
    except Exception:pass


def _profile_warnings(player: dict[str, Any], *, overflow: int, free_attr: int, free_skill: int, current_energy: int, max_energy: int) -> list[dict[str, Any]]:
    """Заметные предупреждения сверху «Обзора» (ТЗ §5)."""
    warnings: list[dict[str, Any]] = []
    try:
        if fine_entries_for_profile(player):
            warnings.append({"type": "fine", "level": "danger", "text": "У вас есть активный штраф."})
    except Exception:
        pass
    negative = [
        e for e in (player.get("active_effects") or [])
        if isinstance(e, dict) and (e.get("kind") == "negative" or e.get("negative") or e.get("is_negative"))
    ]
    if negative:
        warnings.append({"type": "effect", "level": "warning", "text": "На вас действуют отрицательные эффекты."})
    if overflow > 0:
        warnings.append({"type": "overflow", "level": "warning", "text": f"Инвентарь перегружен: {overflow} предметов в дополнительных слотах."})
    if max_energy and current_energy <= max(1, max_energy // 10):
        warnings.append({"type": "energy", "level": "info", "text": "Мало энергии."})
    if free_attr > 0:
        warnings.append({"type": "attr_points", "level": "info", "text": f"Есть свободные очки характеристик: {free_attr}."})
    if free_skill > 0:
        warnings.append({"type": "skill_points", "level": "info", "text": f"Есть свободные очки навыков: {free_skill}."})
    return warnings


def _published_profile_layout() -> dict[str, Any]:
    """Опубликованная раскладка профиля (ТЗ §3, рантайм). Аддитивно и безопасно:
    при любой ошибке/пустоте возвращает пустую раскладку, и профиль работает на
    дефолтных вкладках/оформлении."""
    try:
        from services.profile_layout_service import published_layout
        return published_layout()
    except Exception:  # noqa: BLE001 - раскладка не должна ломать профиль
        return {"tabs": [], "theme": None}


def _referral_summary(player: dict[str, Any]) -> dict[str, Any]:
    """Реферальные данные игрока для профиля (код, ссылка, число приглашённых)."""
    try:
        from services.referral_service import referral_summary
        return referral_summary(player)
    except Exception:  # noqa: BLE001 - реферал не должен ломать профиль
        return {"code": "", "link": "", "count": 0, "referredBy": ""}


def frontend_profile(player: dict[str, Any]) -> dict[str, Any]:
    prune_expired_effects(player)
    ensure_curse_bearer_effect(player)
    refresh_unlocked_active_skills(player)
    recalculate_inventory_overflow(player)
    derived = calculate_player_derived_stats(player)
    level = derived["level"]
    bonus_modifiers = derived.get("bonus_modifiers", {})
    eff = {
        "strength": derived["strength"],
        "endurance": derived["endurance"],
        "agility": derived["dexterity"],
        "dexterity": derived["dexterity"],
        "perception": derived["perception"],
        "intelligence": derived["intelligence"],
        "wisdom": derived["wisdom"],
    }
    hp_max = derived["max_hp"]
    spirit_max = derived["max_spirit"]
    mana_max = derived["max_mana"]
    physical_defense = derived["physical_defense"]
    magic_defense = derived["magic_defense"]
    accuracy = derived["accuracy"]
    dodge = derived["dodge"]
    crit_chance_percent = derived["crit_chance_percent"]
    crit_damage = derived["crit_damage_percent"]
    max_energy = derived["max_energy"]
    current_energy = derived["current_energy"]

    attributes = []
    derived_stat_values = {
        "strength": derived["strength"],
        "endurance": derived["endurance"],
        "dexterity": derived["dexterity"],
        "perception": derived["perception"],
        "intelligence": derived["intelligence"],
        "wisdom": derived["wisdom"],
    }
    for front_key, back_key, label, description in ATTRIBUTE_META:
        base = safe_int((player.get("stats") or {}).get(back_key), 0)
        invested = safe_int((player.get("invested_stats") or {}).get(back_key), 0)
        bonus = safe_int((player.get("stat_bonuses") or {}).get(back_key), 0) + equipment_stat_bonus(bonus_modifiers, back_key)
        attributes.append({
            "key": front_key,
            "label": label,
            "value": derived_stat_values[back_key],
            "base": base,
            "invested": invested,
            "bonus": bonus,
            "description": description,
        })

    from services.item_constructor_service import PROFILE_ACTION_LABELS

    def configured_profile_actions(item: dict[str, Any]) -> set[str] | None:
        raw = item.get("profile_actions")
        return {str(action) for action in raw} if isinstance(raw, list) else None

    def drop_error(item: dict[str, Any]) -> str | None:
        configured = configured_profile_actions(item)
        if configured is not None and "drop" not in configured:
            return "Выбрасывание этого предмета отключено в настройках."
        if item.get("protected") or item.get("drop_protected") or item.get("locked"):
            return "Защищённый предмет нельзя выбросить."
        return None

    equipment = {}
    for slot_key, raw_item in (player.get("equipment") or {}).items():
        if not isinstance(raw_item, dict):
            continue
        item = normalize_item(raw_item, raw_item.get("category", "Снаряжение"))
        item["slotKey"] = slot_key
        configured = configured_profile_actions(item)
        item["actions"] = ["Снять"] if configured is None or "unequip" in configured else []
        equipment[slot_key] = item

    inventory = []
    market_sell_enabled = is_profile_market_sell_enabled(player)
    sellable_stack_indexes = sellable_inventory_stack_indexes(player) if market_sell_enabled else set()
    for inventory_index, raw_item in enumerate(player.get("inventory", [])):
        if not isinstance(raw_item, dict):
            continue
        item = normalize_item(raw_item)
        item["inventoryIndex"] = inventory_index
        configured = configured_profile_actions(item)
        if is_profile_equipment_item(item) and (configured is None or "equip" in configured):
            item["actions"] = ["Надеть"]
        elif is_inventory_item_usable(item) and (configured is None or "open" in configured or "use" in configured):
            item["actions"] = ["Открыть" if item.get("can_open") and (configured is None or "open" in configured) else "Использовать"]
        else:
            item.setdefault("actions", [])
        if inventory_index in sellable_stack_indexes and (configured is None or "sell" in configured):
            item.setdefault("actions", [])
            if "Продать" not in item["actions"]:
                item["actions"].append("Продать")
            item["marketSellAvailable"] = True
        current_durability = safe_int(item.get("current_durability", item.get("durability")), 0)
        max_durability = safe_int(item.get("max_durability", item.get("durability_max")), 0)
        if item.get("can_be_repaired") and max_durability > 0 and current_durability < max_durability and (configured is None or "repair" in configured):
            item.setdefault("actions", []).append("Ремонт")
        if configured is not None:
            for action in ("inspect", "read", "charge", "discharge", "pouch_store", "pouch_remove", "storage_store", "transfer", "delivery"):
                if action in configured:
                    if action == "pouch_store" and item.get("in_pouch") or action == "pouch_remove" and not item.get("in_pouch"):
                        continue
                    charges = safe_int(item.get("current_charges", item.get("charges")), 0)
                    maximum_charges = safe_int(item.get("max_charges"), 0)
                    if action == "charge" and maximum_charges and charges >= maximum_charges or action == "discharge" and charges <= 0:
                        continue
                    item.setdefault("actions", []).append(PROFILE_ACTION_LABELS[action])
        item["profileCanDrop"] = drop_error(item) is None
        item["dropWarning"] = "Особый предмет будет потерян безвозвратно." if any((item.get("is_quest"), item.get("quest_item"), item.get("is_unique"), item.get("unique"), item.get("cursed"), item.get("ancient"))) else ""
        try:
            from services.craft_operation_runtime import available_rules
            item["craftOperations"] = available_rules(item)
            if configured is not None:
                operation_action = {"upgrade": "upgrade", "enchant": "enchant", "repair": "repair", "disassemble": "disassemble", "purify": "disassemble"}
                item["craftOperations"] = [row for row in item["craftOperations"] if operation_action.get(str(row.get("operation") or ""), str(row.get("operation") or "")) in configured]
        except Exception:
            item["craftOperations"] = []
        inventory.append(item)

    skills = player.get("skills", {}) if isinstance(player.get("skills"), dict) else {}
    equipped_skills = [normalize_skill(skill, level, bonus_modifiers, "equipped", player) for skill in skills.get("equipped", []) if isinstance(skill, dict)]
    equipped_skill_keys = {str(skill.get("id") or skill.get("name") or "") for skill in equipped_skills}
    active_skills = [
        normalize_skill(skill, level, bonus_modifiers, "active", player)
        for skill in skills.get("active", [])
        if isinstance(skill, dict) and str(skill.get("id") or skill.get("name") or "") not in equipped_skill_keys
    ]
    passive_skills = [
        normalize_skill(skill, level, bonus_modifiers, "passive", player)
        for skill in skills.get("passive", [])
        if isinstance(skill, dict) and str(skill.get("id") or skill.get("name") or "") not in equipped_skill_keys
    ]
    passive_equipped_skills = [
        normalize_skill(skill, level, bonus_modifiers, "passive_equipped", player)
        for skill in skills.get("passive_equipped", [])
        if isinstance(skill, dict)
    ]

    crafting_levels = []
    for key, value in (player.get("crafting_levels") or {}).items():
        if isinstance(value, dict):
            crafting_levels.append({"name": CRAFT_LABELS.get(key, key), "level": safe_int(value.get("level"), 1), "exp": f"{safe_int(value.get('experience'), 0)} опыта"})

    race_key = RACE_MODEL_KEYS.get(str(player.get("race_id", "human")), str(player.get("race_id", "human")))

    # Новые data-driven блоки профиля V2 (ТЗ §19) — добавляются поверх старых
    # ключей, поэтому текущий фронт продолжает работать без изменений.
    profile_warnings = _profile_warnings(
        player,
        overflow=overflow_slot_count(player),
        free_attr=safe_int(player.get("free_stat_points"), 0),
        free_skill=safe_int(player.get("free_skill_points"), 0),
        current_energy=current_energy,
        max_energy=max_energy,
    )

    return {
        "profileSchemaVersion": PROFILE_SCHEMA_VERSION,
        "status": _profile_status(player),
        "warnings": profile_warnings,
        "ratingPlaces": _profile_rating_places(player),
        "reputations": _profile_reputations(player),
        "eventCampaigns": _profile_event_campaigns(player),
        "services": _profile_services(player),
        "guild": _profile_guild(player),
        "profileLayout": _published_profile_layout(),
        "assets": {
            "background": "/assets/profile/backgrounds/1.png",
            "raceModels": {
                "human": "/assets/profile/models/human.png",
                "elf": "/assets/profile/models/elf.png",
                "dwarf": "/assets/profile/models/dwarf.png",
                "undead": "/assets/profile/models/undead.png",
                "lizardfolk": "/assets/profile/models/lizardfolk.png",
            },
        },
        "player": {
            "userGlobalId": player.get("game_id") or player.get("id"),
            "publicId": player.get("public_id"),
            "nickname": player.get("name", "Безымянный"),
            "raceKey": race_key,
            "raceName": player.get("race_name", "Человек"),
            "raceInfo": _profile_race_info(race_key),
            "raceChangeOptions": [{"id": rid, "name": row.get("name") or rid,
                                   "warning": row.get("change_warning_text") or "⚠️ Смена расы заменит постоянные бонусы.",
                                   "cost": safe_int(row.get("change_cost"), 0)}
                                  for rid, row in _races_catalog().items() if rid != race_key and row.get("change_allowed") and row.get("change_via_service")],
            "gender": player.get("gender", "not_selected"),
            "genderLabel": gender_label_ru(player.get("gender"), player.get("gender_label")),
            "profileFieldEdits": profile_field_edit_availability(player),
            "branch": player_branch(player) or "Без ветви",
            "skillBranch": player_branch(player) or "Без ветви",
            "mainSkillPath": selected_main_path(player),
            "mainSkillPathLevel": path_level(player, selected_main_path(player) or ""),
            "secondarySkillPath": selected_secondary_path(player),
            "secondarySkillPathLevel": path_level(player, selected_secondary_path(player) or ""),
            "secondarySkillPathLimit": secondary_path_limit(player),
            "level": level,
            "experienceCurrent": safe_int(player.get("experience"), 0),
            "experienceToNext": safe_int(player.get("experience_to_next"), max(100, level * 100)),
            "freeAttributePoints": safe_int(player.get("free_stat_points"), 0),
            "freeSkillPoints": safe_int(player.get("free_skill_points"), 0),
            "balanceText": format_money(safe_int(player.get("money"), 0)),
            "registrationDate": format_date(player.get("created_at")),
            "inventoryCapacity": max_regular_slots(player),
            "inventoryUsedSlots": regular_slot_count(player),
            "inventoryFreeSlots": max(0, max_regular_slots(player) - regular_slot_count(player)),
            "inventoryOverflowCapacity": max_overflow_slots(player),
            "inventoryOverflowUsed": overflow_slot_count(player),
            "inventoryOverflowFree": max(0, max_overflow_slots(player) - overflow_slot_count(player)),
            "inventoryOverloaded": overflow_slot_count(player) > 0,
            "inventoryNoEscape": bool(player.get("inventory_overflow_no_escape")),
            "skillEquipCapacity": safe_int(player.get("skill_equip_capacity") or player.get("max_equipped_skills"), 2),
            "skillEquipUsed": len(equipped_skills),
            "skillEquipFree": max(0, safe_int(player.get("skill_equip_capacity") or player.get("max_equipped_skills"), 2) - len(equipped_skills)),
            "passiveSkillSlots": safe_int(player.get("passive_skill_slots"), 2),
            "passiveSkillSlotsUsed": sum(max(1, safe_int(row.get("passive_slot_cost"), 1)) for row in skills.get("passive_equipped", []) if isinstance(row, dict)),
        },
        "attributes": attributes,
        "parameters": [
            {"label": "HP", "value": f"{safe_int(player.get('hp'), hp_max)} / {hp_max}"},
            {"label": "Дух", "value": f"{safe_int(player.get('spirit'), spirit_max)} / {spirit_max}"},
            {"label": "Мана", "value": f"{safe_int(player.get('mana'), mana_max)} / {mana_max}"},
            {"label": "Энергия", "value": f"{current_energy} / {max_energy}"},
            {"label": "Физическая защита", "value": physical_defense},
            {"label": "Магическая защита", "value": magic_defense},
            {"label": "Точность", "value": accuracy},
            {"label": "Уклонение", "value": dodge},
            {"label": "Шанс крита", "value": f"{crit_chance_percent}%"},
            {"label": "Урон крита", "value": f"{crit_damage}%"},
        ],
        "effects": [effect for effect in (normalize_effect_for_frontend(raw_effect) for raw_effect in [*player.get("active_effects", []), *_battle_stimulant_status_effects(player)]) if effect],
        "activeSets": player.get("active_sets", []),
        "equipmentSlots": equipment_slots_for_frontend(player.get("equipment") or {}, player=player),
        "equipment": equipment,
        "inventory": inventory,
        "personalStorage": [dict(normalize_item(item), storageIndex=index) for index, item in enumerate(player.get("personal_storage") or []) if isinstance(item, dict)],
        "craftDelivery": {"pendingAmount": sum(int(row.get("amount") or 0) for row in player.get("craft_delivery_inbox") or [] if isinstance(row, dict))},
        "market": {
            "sellFromProfile": market_sell_enabled,
            "sellButtonLabel": "Продать",
        },
        "skills": {"active": active_skills, "equipped": equipped_skills, "passive": passive_skills, "passiveEquipped": passive_equipped_skills},
        "courier": {
            "deliveryCostCopper": courier_delivery_cost_copper(level),
            "deliveryCostText": format_price(courier_delivery_cost_copper(level)),
            "warningText": courier_warning_text(level),
            "letterMaxLength": COURIER_LETTER_MAX_LENGTH,
            "balanceCopper": safe_int(player.get("money"), 0),
            "balanceText": format_money(safe_int(player.get("money"), 0)),
        },
        "referral": _referral_summary(player),
        "information": {
            "achievements": player.get("achievements", []),
            "rating": player.get("rating", {"globalPlace": "—", "pvePlace": "—", "pvpPlace": "—", "craftPlace": "—"}),
            "activity": {"pveKills": safe_int(player.get("pve_kills"), 0), "pvpKills": safe_int(player.get("pvp_kills"), 0), "soulParticlesAbsorbed": safe_int(player.get("soul_particles_absorbed"), 0), "fines": fine_summary_for_profile(player), "fineList": fine_entries_for_profile(player), "craftingLevels": crafting_levels},
        },
    }


def get_player_by_public_id(storage: Any, public_id: str) -> dict[str, Any] | None:
    if hasattr(storage, "get_player_by_public_id"):
        player = storage.get_player_by_public_id(public_id)
        if player is not None:
            return player
    for player in (storage.load().get("players") or {}).values():
        if isinstance(player, dict) and str(player.get("public_id")) == str(public_id):
            return player
    return None


def bearer_token_from_request(request: Request | None) -> str:
    if request is None:
        return ""
    authorization = str(request.headers.get("authorization") or "").strip()
    if not authorization:
        return ""
    scheme, _, value = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not value.strip():
        return ""
    return value.strip()


def profile_identifier_from_request(identifier: str, request: Request | None = None) -> str:
    bearer = bearer_token_from_request(request)
    if bearer:
        return bearer
    return str(identifier or "").strip()


# Профильные write/read-эндпоинты принимают и обычный профиль-токен игрока, и
# админский edit-токен (отдельный scope, чтобы не разлогинивать игрока).
PROFILE_WRITE_SCOPES = (PROFILE_SCOPE, ADMIN_PROFILE_EDIT_SCOPE)


def get_session_and_player_by_token(storage: Any, token: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if hasattr(storage, "get_player_by_web_token"):
        # Перебираем разрешённые scope'ы по очереди (а не scope=None), чтобы
        # одноразовый токен ЧУЖОГО scope (например, павильона) не активировался
        # как побочный эффект при обращении к профильному эндпоинту.
        for allowed_scope in PROFILE_WRITE_SCOPES:
            player, session = storage.get_player_by_web_token(token, scope=allowed_scope)
            if player is not None and session is not None:
                return player, session
        return None, None
    data = storage.load()
    sessions = data.get("web_sessions") or data.get("site_sessions") or {}
    session = sessions.get(token)
    if not session or session.get("scope") not in PROFILE_WRITE_SCOPES:
        return None, None
    expires_at = parse_datetime(session.get("expires_at"))
    if expires_at and expires_at <= datetime.now(timezone.utc):
        return None, None
    player = (data.get("players") or {}).get(session.get("game_id"))
    return player, session if player else None


def resolve_profile_read(storage: Any, identifier: str, request: Request | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    effective_identifier = profile_identifier_from_request(identifier, request)
    player, session = get_session_and_player_by_token(storage, effective_identifier)
    if player is not None and session is not None:
        return player, session
    # Public IDs no longer expose the full React profile JSON. The website
    # profile API is private and requires a bot-issued token/active session.
    raise HTTPException(status_code=401, detail="Профиль доступен только по свежей ссылке из бота.")


def resolve_profile_write(storage: Any, identifier: str, request: Request | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    effective_identifier = profile_identifier_from_request(identifier, request)
    player, session = get_session_and_player_by_token(storage, effective_identifier)
    if player is None or session is None:
        raise HTTPException(status_code=401, detail="Действие доступно только по активной временной ссылке из бота.")
    try:
        settings=(_published_profile_layout().get("settings") or {})
        if settings.get("allow_profile_edit") is False:raise HTTPException(status_code=403,detail=str(settings.get("readonly_text") or "Профиль доступен только для просмотра."))
    except HTTPException:raise
    except Exception:pass
    return player, session


def frontend_profile_payload(player: dict[str, Any], session: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = frontend_profile(player)
    if session:
        token = session.get("token")
        if token:
            payload["sessionToken"] = token
        if session.get("expires_at"):
            payload["sessionExpiresAt"] = session.get("expires_at")
    return payload


def save_player(storage: Any, player: dict[str, Any]) -> None:
    if hasattr(storage, "update_player"):
        storage.update_player(player)
        return
    data = storage.load()
    game_id = player.get("game_id") or player.get("id")
    if not game_id:
        raise HTTPException(status_code=500, detail="Нельзя сохранить игрока без game_id.")
    data.setdefault("players", {})[game_id] = player
    storage.save(data)


def sync_player_parameters_for_bots(player: dict[str, Any]) -> None:
    """Persist derived resources so bot messages use current profile values."""

    ensure_player_resources(player)


def skill_matches(skill: dict[str, Any], skill_id: str) -> bool:
    target = str(skill_id or "").strip()
    return bool(target) and target in {str(skill.get("id") or ""), str(skill.get("name") or "")}


def find_player_skill_with_section(player: dict[str, Any], skill_id: str, sections: tuple[str, ...] = ("active", "equipped", "passive", "passive_equipped")) -> tuple[str, int, dict[str, Any]] | None:
    skills = player.get("skills")
    if not isinstance(skills, dict):
        return None
    for section in sections:
        section_skills = skills.get(section, [])
        if not isinstance(section_skills, list):
            continue
        for index, skill in enumerate(section_skills):
            if isinstance(skill, dict) and skill_matches(skill, skill_id):
                return section, index, skill
    return None


def find_player_skill(player: dict[str, Any], skill_id: str) -> dict[str, Any] | None:
    found = find_player_skill_with_section(player, skill_id)
    return found[2] if found else None


def equip_player_skill(player: dict[str, Any], skill_id: str) -> None:
    skills = player.setdefault("skills", {})
    equipped = skills.setdefault("equipped", [])
    if not isinstance(equipped, list):
        equipped = []
        skills["equipped"] = equipped
    if any(isinstance(skill, dict) and skill_matches(skill, skill_id) for skill in equipped):
        return
    capacity = safe_int(player.get("skill_equip_capacity") or player.get("max_equipped_skills"), 2)
    if len(equipped) >= capacity:
        raise HTTPException(status_code=400, detail="Нет свободных слотов экипированных навыков.")
    found = find_player_skill_with_section(player, skill_id, ("active", "passive"))
    if found is None:
        raise HTTPException(status_code=404, detail="Навык не найден.")
    source_section, index, skill = found
    skill_type = str(skill.get("skill_type") or skill.get("type") or "").lower()
    if skill_type in {"passive", "пассивный"}:
        passive_equipped = skills.setdefault("passive_equipped", [])
        cost = max(1, safe_int(skill.get("passive_slot_cost"), 1))
        capacity = max(0, safe_int(player.get("passive_skill_slots"), 2))
        used = sum(max(1, safe_int(row.get("passive_slot_cost"), 1)) for row in passive_equipped if isinstance(row, dict))
        if used + cost > capacity:
            raise HTTPException(status_code=400, detail="Нет свободных пассивных слотов.")
        source_list = skills.get(source_section)
        if isinstance(source_list, list): source_list.pop(index)
        skill["source_section"] = source_section
        passive_equipped.append(skill)
        return
    if source_section == "passive":
        raise HTTPException(status_code=400, detail="Этот пассивный навык нельзя устанавливать в слот.")
    if skill.get("equippable") is False:
        raise HTTPException(status_code=400, detail="Этот навык нельзя экипировать для использования.")
    if not is_skill_weapon_compatible(player, skill):
        raise HTTPException(status_code=400, detail=f"Для этого навыка нужно подходящее оружие: {skill_weapon_requirement_text(skill)}.")
    source_list = skills.get(source_section)
    if isinstance(source_list, list):
        source_list.pop(index)
    skill["source_section"] = source_section
    equipped.append(skill)


def unequip_player_skill(player: dict[str, Any], skill_id: str) -> None:
    skills = player.setdefault("skills", {})
    found = find_player_skill_with_section(player, skill_id, ("equipped", "passive_equipped"))
    if found is None:
        raise HTTPException(status_code=404, detail="Экипированный навык не найден.")
    _section, index, skill = found
    equipped = skills.get(_section, [])
    if isinstance(equipped, list):
        equipped.pop(index)
    target_section = skill.pop("source_section", None) or ("passive" if str(skill.get("skill_type") or "").lower() in {"passive", "пассивный"} else "active")
    skills.setdefault(target_section, []).append(skill)




TWO_HANDED_TRUE_VALUES = {"1", "true", "yes", "да", "двуручное", "двуручный", "two_handed", "two-handed", "2h"}


def _truthy_equipment_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    return str(value or "").strip().casefold() in TWO_HANDED_TRUE_VALUES


def is_two_handed_equipment(item: dict[str, Any] | None) -> bool:
    if not isinstance(item, dict):
        return False
    combat = item.get("combat") if isinstance(item.get("combat"), dict) else {}
    raw_values = (
        item.get("two_handed"),
        item.get("twoHanded"),
        item.get("is_two_handed"),
        item.get("isTwoHanded"),
        item.get("requires_two_hands"),
        combat.get("two_handed"),
        combat.get("twoHanded"),
        combat.get("requires_two_hands"),
    )
    if any(_truthy_equipment_flag(value) for value in raw_values):
        return True
    hands = item.get("hands") or combat.get("hands") or item.get("hand_count") or combat.get("hand_count")
    if safe_int(hands, 0) >= 2:
        return True
    text = " ".join(str(item.get(key) or "") for key in ("name", "type", "subtype", "description", "slot", "slotKey", "targetSlotKey")).casefold()
    return "двуруч" in text or "two-handed" in text or "two handed" in text or "two_handed" in text


def equipment_weapon_token(item: dict[str, Any] | None) -> str:
    if not isinstance(item, dict):
        return ""
    values = (
        item.get("weapon_type"),
        item.get("weaponType"),
        item.get("subtype"),
        item.get("type"),
        item.get("category"),
        item.get("id"),
        item.get("item_id"),
        item.get("name"),
    )
    text = " ".join(str(value or "") for value in values).casefold()
    if "crossbow" in text or "арбалет" in text:
        return "crossbow"
    if "bow" in text or "лук" in text:
        return "bow"
    if "staff" in text or "посох" in text:
        return "staff"
    if "sword" in text or "меч" in text:
        return "sword"
    if "dagger" in text or "кинжал" in text:
        return "dagger"
    if "axe" in text or "топор" in text:
        return "axe"
    if "hammer" in text or "mace" in text or "молот" in text or "булава" in text:
        return "hammer"
    if "shield" in text or "щит" in text:
        return "shield"
    return ""


def quiver_kind(item: dict[str, Any] | None) -> str:
    if not isinstance(item, dict):
        return ""
    item_id = str(item.get("id") or item.get("item_id") or "").strip()
    raw = " ".join(str(item.get(key) or "") for key in ("quiver_type", "subtype", "type", "slot", "targetSlotKey", "name")).casefold()
    if item_id == "arrow_quiver_empty" or "arrow_quiver" in raw or "стрел" in raw:
        return "arrow_quiver"
    if item_id == "bolt_quiver_empty" or "bolt_quiver" in raw or "болт" in raw:
        return "bolt_quiver"
    return "quiver" if "колчан" in raw or "quiver" in raw else ""


def is_quiver_item(item: dict[str, Any] | None) -> bool:
    return bool(quiver_kind(item))


def required_weapon_for_quiver(item: dict[str, Any] | None) -> str:
    kind = quiver_kind(item)
    if kind == "arrow_quiver":
        return "bow"
    if kind == "bolt_quiver":
        return "crossbow"
    return ""


def is_matching_quiver_for_weapon(item: dict[str, Any] | None, weapon: dict[str, Any] | None) -> bool:
    required = required_weapon_for_quiver(item)
    return bool(required and equipment_weapon_token(weapon) == required)


def quiver_equip_error(item: dict[str, Any] | None, equipment: dict[str, Any]) -> str:
    required = required_weapon_for_quiver(item)
    if required == "bow":
        return "Колчан для стрел можно надеть во второй оружейный слот только если в первом слоте экипирован лук."
    if required == "crossbow":
        return "Колчан для болтов можно надеть во второй оружейный слот только если в первом слоте экипирован арбалет."
    return "Колчан можно надеть только во второй оружейный слот при подходящем оружии в первом слоте."


def weapon2_has_ranged_quiver_mode(equipment: dict[str, Any] | None) -> bool:
    if not isinstance(equipment, dict):
        return False
    weapon1 = equipment.get("weapon1")
    return isinstance(weapon1, dict) and equipment_weapon_token(weapon1) in {"bow", "crossbow"}


def weapon2_restricted_by_two_handed_ranged(equipment: dict[str, Any] | None) -> bool:
    if not isinstance(equipment, dict):
        return False
    weapon1 = equipment.get("weapon1")
    return isinstance(weapon1, dict) and is_two_handed_equipment(weapon1) and equipment_weapon_token(weapon1) in {"bow", "crossbow"}


def weapon2_blocking_item(equipment: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(equipment, dict):
        return None
    weapon1 = equipment.get("weapon1")
    if isinstance(weapon1, dict) and is_two_handed_equipment(weapon1) and equipment_weapon_token(weapon1) not in {"bow", "crossbow"}:
        return weapon1
    return None


def weapon2_blocked_reason(equipment: dict[str, Any] | None) -> str:
    item = weapon2_blocking_item(equipment)
    if not item:
        return ""
    return f"Второй оружейный слот заблокирован: {item.get('name') or 'двуручное оружие'} занимает обе руки."


def equipment_slots_for_frontend(equipment: dict[str, Any] | None, *, player: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    slots = deepcopy(EQUIPMENT_SLOTS)
    reason = weapon2_blocked_reason(equipment)
    if reason:
        for slot in slots:
            if slot.get("key") == "weapon2":
                slot["blocked"] = True
                slot["blockedBy"] = "weapon1"
                slot["blockedReason"] = reason
                slot["label"] = "Оружие 2"
                slot["statusLabel"] = "заблокировано"
                break
    elif weapon2_has_ranged_quiver_mode(equipment):
        weapon1 = (equipment or {}).get("weapon1") if isinstance(equipment, dict) else None
        weapon_token = equipment_weapon_token(weapon1)
        for slot in slots:
            if slot.get("key") == "weapon2":
                slot["label"] = "Оружие 2 / Колчан"
                slot["statusLabel"] = "только колчан"
                slot["restricted"] = True
                slot["restrictedReason"] = "Во второй слот можно надеть только подходящий колчан."
                slot["expectedQuiver"] = "arrow_quiver" if weapon_token == "bow" else "bolt_quiver"
                break
    if player:
        try:
            from services.effect_runtime_service import blocked_slots
            for slot in slots:
                blocked_reason = blocked_slots(player).get(str(slot.get("key") or ""))
                if blocked_reason:
                    slot["blocked"] = True
                    slot["blockedBy"] = "trauma"
                    slot["blockedReason"] = blocked_reason
                    slot["statusLabel"] = "заблокировано травмой"
        except Exception:
            pass
    return slots


def _strip_inventory_storage_markers(item: dict[str, Any]) -> None:
    for key in (
        "overflow_slot",
        "storage_type",
        "inventory_status",
        "overflowSlot",
        "inventoryStatus",
    ):
        item.pop(key, None)


def prepare_item_for_inventory_from_slot(item: dict[str, Any], slot_key: str) -> dict[str, Any]:
    item = deepcopy(item)
    item["targetSlotKey"] = slot_key
    item.pop("slotKey", None)
    _strip_inventory_storage_markers(item)
    return item


def _add_inventory_item_or_raise(player: dict[str, Any], item: dict[str, Any], amount: int, detail: str) -> None:
    result = add_inventory_item(player, item, amount)
    if safe_int(getattr(result, "discarded", 0), 0) > 0 or safe_int(getattr(result, "added", 0), 0) < amount:
        raise HTTPException(status_code=400, detail=detail)


def validate_equipment_level_requirement(player: dict[str, Any], item: dict[str, Any]) -> None:
    if not is_levelled_equipment_item(item):
        return
    item_level = max(1, safe_int(item.get("level") or item.get("required_level"), 1))
    player_level = max(1, safe_int(player.get("level"), 1))
    if item_level > player_level + 3:
        raise HTTPException(
            status_code=400,
            detail=f"Уровень предмета слишком высок: требуется не выше {player_level + 3}, у предмета {item_level}.",
        )


def compatible_equipment_slot(item: dict[str, Any], requested_slot: str | None, equipment: dict[str, Any]) -> str:
    raw_slot = str(item.get("targetSlotKey") or item.get("slotKey") or item.get("slot") or item.get("target_slot") or "").strip()
    item_type = str(item.get("type") or item.get("subtype") or item.get("category") or "").casefold()
    requested = str(requested_slot or "").strip()
    is_two_handed = is_two_handed_equipment(item)
    weapon2_blocked = weapon2_blocking_item(equipment) is not None
    weapon2_ranged_restricted = weapon2_restricted_by_two_handed_ranged(equipment) or weapon2_has_ranged_quiver_mode(equipment)
    is_quiver = is_quiver_item(item)

    def ensure_quiver_allowed() -> str:
        if requested and requested != "weapon2":
            raise HTTPException(status_code=400, detail="Колчан можно экипировать только во второй оружейный слот.")
        weapon1 = equipment.get("weapon1") if isinstance(equipment, dict) else None
        if not is_matching_quiver_for_weapon(item, weapon1):
            raise HTTPException(status_code=400, detail=quiver_equip_error(item, equipment))
        if isinstance(equipment.get("weapon2"), dict) and not requested:
            return "weapon2"
        return "weapon2"

    if is_quiver:
        return ensure_quiver_allowed()

    def first_free(options: tuple[str, ...]) -> str:
        for slot in options:
            if slot == "weapon2" and (weapon2_blocked or weapon2_ranged_restricted):
                continue
            if not isinstance(equipment.get(slot), dict):
                return slot
        if "weapon1" in options:
            return "weapon1"
        return options[0]

    if raw_slot in {"ring1", "ring2"}:
        allowed = (raw_slot,)
    elif raw_slot == "ring" or "кольцо" in item_type or item_type == "ring":
        allowed = ("ring1", "ring2")
    elif raw_slot in {"weapon1", "weapon2"}:
        allowed = ("weapon1",) if is_two_handed else (raw_slot,)
    elif raw_slot in {"weapon", "main_hand", "off_hand"} or item_type in {"оружие", "weapon", "меч", "посох", "кинжал", "топор", "молот", "булава", "лук", "арбалет"}:
        allowed = ("weapon1",) if is_two_handed else ("weapon1", "weapon2")
    elif raw_slot in {"arrow_quiver", "bolt_quiver"}:
        raise HTTPException(status_code=400, detail="Колчаны теперь экипируются во второй оружейный слот при подходящем оружии в первом слоте.")
    elif raw_slot:
        allowed = (raw_slot,)
    else:
        raise HTTPException(status_code=400, detail="У предмета не указан слот экипировки.")

    if requested:
        if requested == "weapon2" and weapon2_blocked:
            raise HTTPException(status_code=400, detail=weapon2_blocked_reason(equipment))
        if requested == "weapon2" and weapon2_ranged_restricted:
            raise HTTPException(status_code=400, detail="Во второй слот при луке или арбалете можно надеть только подходящий колчан.")
        if is_two_handed and requested == "weapon2":
            raise HTTPException(status_code=400, detail="Двуручное оружие можно надеть только в первый оружейный слот: второй слот оно блокирует.")
        if requested not in allowed:
            raise HTTPException(status_code=400, detail="Выбранный слот не подходит для этого предмета.")
        return requested
    return first_free(allowed)


def unequip_incompatible_weapon2(
    player: dict[str, Any],
    previous_slot: str | None = None,
    *,
    fail_on_discard: bool = False,
) -> None:
    equipment = player.setdefault("equipment", {})
    weapon2 = equipment.get("weapon2")
    if not isinstance(weapon2, dict):
        return
    weapon1 = equipment.get("weapon1")
    should_unequip = False
    if is_quiver_item(weapon2):
        should_unequip = not is_matching_quiver_for_weapon(weapon2, weapon1)
    elif weapon2_blocking_item(equipment) is not None or weapon2_restricted_by_two_handed_ranged(equipment):
        should_unequip = True
    if should_unequip:
        returned = prepare_item_for_inventory_from_slot(weapon2, "weapon2")
        amount = safe_int(returned.get("amount"), 1)
        if fail_on_discard:
            _add_inventory_item_or_raise(
                player,
                returned,
                amount,
                "Нельзя снять или заменить оружие: во втором слоте находится несовместимый предмет, "
                "а в инвентаре и доп. слотах нет места, чтобы безопасно убрать его.",
            )
        else:
            add_inventory_item(player, returned, amount)
        equipment.pop("weapon2", None)

AMMO_LOAD_RULES = {
    "arrow_for_bow": {
        "quiver_slot": "weapon2",
        "quiver_kind": "arrow_quiver",
        "quiver_item_id": "arrow_quiver_empty",
        "ammo_item_id": "arrow_for_bow",
        "ammo_name": "стрел",
        "capacity": 30,
        "missing_message": "Сначала экипируйте колчан для стрел или положите его в инвентарь.",
    },
    "bolt_for_crossbow": {
        "quiver_slot": "weapon2",
        "quiver_kind": "bolt_quiver",
        "quiver_item_id": "bolt_quiver_empty",
        "ammo_item_id": "bolt_for_crossbow",
        "ammo_name": "болтов",
        "capacity": 30,
        "missing_message": "Сначала экипируйте колчан для болтов или положите его в инвентарь.",
    },
}


def item_identity(item: dict[str, Any] | None) -> str:
    if not isinstance(item, dict):
        return ""
    return str(item.get("id") or item.get("item_id") or "").strip()


def is_ammunition_item(item: dict[str, Any] | None) -> bool:
    item_id = item_identity(item)
    if item_id in AMMO_LOAD_RULES:
        return True
    text = " ".join(str(item.get(key) or "") for key in ("type", "subtype", "category", "name") if isinstance(item, dict)).casefold()
    return "боеприп" in text or "ammunition" in text


def _quiver_capacity_for_rule(quiver: dict[str, Any], rule: dict[str, Any]) -> int:
    base_capacity = max(1, safe_int(rule.get("capacity"), 1))
    current_capacity = safe_int(quiver.get("capacity"), 0)
    # Базовые пустые колчаны могут получить увеличенную вместимость после обновления данных.
    # Поэтому при загрузке не оставляем старые экземпляры с устаревшей меньшей вместимостью.
    if item_identity(quiver) == str(rule.get("quiver_item_id") or ""):
        return max(base_capacity, current_capacity)
    return max(1, current_capacity or base_capacity)


def sync_quiver_ammo_stats(quiver: dict[str, Any], rule: dict[str, Any] | None = None) -> None:
    if not isinstance(quiver, dict):
        return
    capacity = safe_int(quiver.get("capacity"), 0)
    if rule is not None:
        capacity = _quiver_capacity_for_rule(quiver, rule)
        quiver["capacity"] = capacity
        quiver.setdefault("ammo_item_id", rule.get("ammo_item_id"))
    ammo_count = max(0, safe_int(quiver.get("ammo_count"), 0))
    quiver["ammo_count"] = min(ammo_count, capacity) if capacity > 0 else ammo_count
    stats = quiver.get("stats")
    if not isinstance(stats, list):
        stats = []
    stats = [line for line in stats if "заряжено" not in str(line).casefold()]
    if capacity > 0:
        stats.append(f"Заряжено: {quiver['ammo_count']}/{capacity}")
    quiver["stats"] = stats


def _find_reloadable_quiver(player: dict[str, Any], rule: dict[str, Any]) -> tuple[dict[str, Any] | None, str, bool]:
    required_kind = str(rule.get("quiver_kind") or "")
    required_ammo_id = str(rule.get("ammo_item_id") or "")
    full_quiver_seen = False

    def is_compatible(candidate: Any) -> bool:
        if not isinstance(candidate, dict) or quiver_kind(candidate) != required_kind:
            return False
        loaded_ammo_id = str(candidate.get("ammo_item_id") or required_ammo_id)
        return loaded_ammo_id == required_ammo_id

    equipment = player.setdefault("equipment", {})
    equipped_candidates = []
    for slot in (str(rule.get("quiver_slot") or "weapon2"), required_kind):
        candidate = equipment.get(slot)
        if isinstance(candidate, dict) and all(candidate is not seen for seen in equipped_candidates):
            equipped_candidates.append(candidate)
    for equipped in equipped_candidates:
        if is_compatible(equipped):
            sync_quiver_ammo_stats(equipped, rule)
            capacity = _quiver_capacity_for_rule(equipped, rule)
            if max(0, safe_int(equipped.get("ammo_count"), 0)) < capacity:
                return equipped, "экипированный колчан", full_quiver_seen
            full_quiver_seen = True

    inventory = player.setdefault("inventory", [])
    for candidate in inventory:
        if not is_compatible(candidate):
            continue
        sync_quiver_ammo_stats(candidate, rule)
        capacity = _quiver_capacity_for_rule(candidate, rule)
        if max(0, safe_int(candidate.get("ammo_count"), 0)) < capacity:
            return candidate, "колчан в инвентаре", full_quiver_seen
        full_quiver_seen = True

    return None, "", full_quiver_seen


def load_ammo_into_quiver(player: dict[str, Any], item: dict[str, Any], amount: int) -> tuple[int, str]:
    item_id = item_identity(item)
    rule = AMMO_LOAD_RULES.get(item_id)
    if not rule:
        raise HTTPException(status_code=400, detail="Этот боеприпас нельзя загрузить в колчан.")
    quiver, location_label, full_quiver_seen = _find_reloadable_quiver(player, rule)
    if not isinstance(quiver, dict):
        if full_quiver_seen:
            raise HTTPException(status_code=400, detail="Колчан уже заполнен.")
        raise HTTPException(status_code=400, detail=rule["missing_message"])
    quiver.setdefault("ammo_item_id", rule["ammo_item_id"])
    if str(quiver.get("ammo_item_id") or "") != rule["ammo_item_id"]:
        raise HTTPException(status_code=400, detail="Этот боеприпас не подходит к выбранному колчану.")
    capacity = _quiver_capacity_for_rule(quiver, rule)
    current = max(0, safe_int(quiver.get("ammo_count"), 0))
    free = max(0, capacity - current)
    if free <= 0:
        raise HTTPException(status_code=400, detail="Колчан уже заполнен.")
    loaded = min(max(1, safe_int(amount, 1)), free)
    quiver["capacity"] = capacity
    quiver["ammo_count"] = current + loaded
    quiver["ammo_item_id"] = rule["ammo_item_id"]
    sync_quiver_ammo_stats(quiver, rule)
    return loaded, f"В {location_label} загружено: {rule['ammo_name']} ×{loaded}."


# Совместимость для старых импортов/тестов.
load_ammo_into_equipped_quiver = load_ammo_into_quiver


def remove_inventory_amount_at_index(inventory: list[Any], index: int, amount: int) -> None:
    item = inventory[index]
    current = max(1, safe_int(item.get("amount"), 1)) if isinstance(item, dict) else 1
    amount = max(1, safe_int(amount, 1))
    if current > amount:
        item["amount"] = current - amount
    else:
        inventory.pop(index)


def find_inventory_index_for_site_action(inventory: list[Any], item_id: str, inventory_index: int | None = None) -> int | None:
    """Find an inventory stack by UI index when available, with item_id fallback.

    The React profile displays duplicated crafted variants with the same base
    item id. Using the explicit inventory index prevents equipping, using or
    dropping the wrong quality variant while keeping old clients compatible.
    """
    expected_item_id = str(item_id or "").strip()
    if inventory_index is not None:
        if inventory_index < 0 or inventory_index >= len(inventory):
            raise HTTPException(status_code=404, detail="Предмет в инвентаре не найден.")
        item = inventory[inventory_index]
        if not isinstance(item, dict):
            raise HTTPException(status_code=404, detail="Предмет в инвентаре не найден.")
        if item_identity(item) != expected_item_id:
            raise HTTPException(status_code=409, detail="Инвентарь изменился. Обновите профиль и повторите действие.")
        return inventory_index
    return next(
        (
            index
            for index, item in enumerate(inventory)
            if isinstance(item, dict) and item_identity(item) == expected_item_id
        ),
        None,
    )


def inventory_drop_error(item: dict[str, Any]) -> str | None:
    actions = item.get("profile_actions")
    if isinstance(actions, list) and "drop" not in {str(action) for action in actions}:
        return "Выбрасывание этого предмета отключено в настройках."
    if item.get("protected") or item.get("drop_protected") or item.get("locked"):
        return "Защищённый предмет нельзя выбросить."
    return None


def require_configured_profile_action(item: dict[str, Any], *allowed: str) -> None:
    actions = item.get("profile_actions")
    if isinstance(actions, list) and not ({str(action) for action in actions} & set(allowed)):
        raise HTTPException(status_code=400, detail="Это действие отключено для предмета в настройках конструктора.")


def spend_points_on_skill(skill: dict[str, Any], modifier_id: str | None, amount: int) -> None:
    if not skill.get("upgradeable"):
        raise HTTPException(status_code=400, detail="Этот навык нельзя улучшить.")

    modifiers = skill.get("modifiers")
    target_modifier = str(modifier_id or "main").strip()
    if not isinstance(modifiers, list) or not modifiers:
        if target_modifier in {"", "main"}:
            skill["level"] = safe_int(skill.get("level"), 0) + amount
            return
        raise HTTPException(status_code=400, detail="Модификатор навыка не найден.")

    for modifier in modifiers:
        if not isinstance(modifier, dict):
            continue
        modifier_keys = {
            str(modifier.get("id") or ""),
            str(modifier.get("name") or ""),
            str(modifier.get("label") or ""),
        }
        if target_modifier in modifier_keys:
            level_key = "level" if "level" in modifier or "points" not in modifier else "points"
            modifier[level_key] = safe_int(modifier.get(level_key), 0) + amount
            skill["level"] = skill_level(skill)
            return

    raise HTTPException(status_code=400, detail="Модификатор навыка не найден.")


def create_profile_api_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/profile", tags=["profile"])

    def _opened(player, session):
        storage=get_storage()
        try:
            from services.referral_service import process_referral_event
            process_referral_event(storage,player,"profile_open",1)
        except Exception:pass
        return frontend_profile_payload(player,session)

    @router.get("/session/{token}")
    def activate_profile_session(token: str) -> dict[str, Any]:
        player, session = resolve_profile_read(get_storage(), token)
        return _opened(player, session)

    @router.get("/me")
    def get_current_profile(request: Request) -> dict[str, Any]:
        player, session = resolve_profile_read(get_storage(), "", request)
        return _opened(player, session)

    @router.get("/{identifier}")
    def get_profile(identifier: str, request: Request) -> dict[str, Any]:
        player, session = resolve_profile_read(get_storage(), identifier, request)
        return _opened(player, session)

    @router.get("/{identifier}/pavilion-link")
    def get_profile_pavilion_link(identifier:str,request:Request)->dict[str,Any]:
        storage=get_storage();player,session=resolve_profile_read(storage,identifier,request)
        from services.pavilion_runtime import access_active
        if not access_active(player):raise HTTPException(status_code=403,detail="Торговый павильон игроку недоступен.")
        from services.web_profile import create_pavilion_site_link
        return {"ok":True,"url":create_pavilion_site_link(storage,player,str(session.get("platform") or "site"))}

    @router.post("/{identifier}/race/change-preview")
    def preview_race_change(identifier: str, payload: RaceChangePreviewRequest, request: Request) -> dict[str, Any]:
        storage = get_storage(); player, session = resolve_profile_write(storage, identifier, request)
        from services.race_runtime import request_change
        try: preview = request_change(player, payload.target_race_id, method=payload.method)
        except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc
        save_player(storage, player)
        return {"ok": True, "preview": preview, "profile": frontend_profile_payload(player, session)}

    @router.post("/{identifier}/race/change-confirm")
    def confirm_race_change(identifier: str, payload: RaceChangeConfirmRequest, request: Request) -> dict[str, Any]:
        storage = get_storage(); player, session = resolve_profile_write(storage, identifier, request)
        from services.race_runtime import confirm_change
        try: result = confirm_change(player, payload.confirmation_token)
        except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc
        save_player(storage, player)
        return {"ok": True, "result": result, "profile": frontend_profile_payload(player, session)}

    @router.post("/{identifier}/attributes/spend")
    def spend_attribute(identifier: str, payload: SpendAttributeRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        player, session = resolve_profile_write(storage, identifier, request)
        stat_key = FRONT_TO_BACK_STAT.get(payload.attribute_key)
        if not stat_key:
            raise HTTPException(status_code=400, detail="Неизвестная характеристика.")
        free_points = safe_int(player.get("free_stat_points"), 0)
        if payload.amount > free_points:
            raise HTTPException(status_code=400, detail="Недостаточно свободных очков характеристик.")
        player.setdefault("invested_stats", {})[stat_key] = safe_int(player.setdefault("invested_stats", {}).get(stat_key), 0) + payload.amount
        player["free_stat_points"] = free_points - payload.amount
        sync_player_parameters_for_bots(player)
        save_player(storage, player)
        return {"ok": True, "profile": frontend_profile_payload(player, session)}

    @router.post("/{identifier}/attributes/confirm")
    def confirm_attributes(identifier: str, payload: ConfirmAttributeAllocationsRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        player, session = resolve_profile_write(storage, identifier, request)
        if not payload.allocations:
            raise HTTPException(status_code=400, detail="Нет характеристик для подтверждения.")

        normalized_allocations: dict[str, int] = {}
        for front_key, raw_amount in payload.allocations.items():
            stat_key = FRONT_TO_BACK_STAT.get(str(front_key))
            amount = safe_int(raw_amount, 0)
            if not stat_key:
                raise HTTPException(status_code=400, detail="Неизвестная характеристика.")
            if amount <= 0:
                continue
            normalized_allocations[stat_key] = normalized_allocations.get(stat_key, 0) + amount

        total_amount = sum(normalized_allocations.values())
        if total_amount <= 0:
            raise HTTPException(status_code=400, detail="Нет характеристик для подтверждения.")

        free_points = safe_int(player.get("free_stat_points"), 0)
        if total_amount > free_points:
            raise HTTPException(status_code=400, detail="Недостаточно свободных очков характеристик.")

        invested_stats = player.setdefault("invested_stats", {})
        for stat_key, amount in normalized_allocations.items():
            invested_stats[stat_key] = safe_int(invested_stats.get(stat_key), 0) + amount
        player["free_stat_points"] = free_points - total_amount
        refresh_unlocked_active_skills(player)
        sync_player_parameters_for_bots(player)
        save_player(storage, player)
        return {"ok": True, "profile": frontend_profile_payload(player, session)}

    @router.post("/{identifier}/skills/spend")
    def spend_skill(identifier: str, payload: SpendSkillRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        player, session = resolve_profile_write(storage, identifier, request)
        skill = find_player_skill(player, payload.skill_id)
        if skill is None:
            raise HTTPException(status_code=404, detail="Навык не найден.")
        free_points = safe_int(player.get("free_skill_points"), 0)
        upgrade_cost = skill_upgrade_cost(player, skill, payload.amount)
        if upgrade_cost > free_points:
            raise HTTPException(status_code=400, detail=f"Недостаточно свободных очков навыков: нужно {upgrade_cost}.")
        ok, message = can_spend_skill_points_on(player, skill, payload.amount)
        if not ok:
            raise HTTPException(status_code=400, detail=message)
        spend_points_on_skill(skill, payload.modifier_id, payload.amount)
        player["free_skill_points"] = free_points - upgrade_cost
        refresh_unlocked_active_skills(player)
        sync_player_parameters_for_bots(player)
        save_player(storage, player)
        return {"ok": True, "profile": frontend_profile_payload(player, session)}

    @router.post("/{identifier}/skills/equip")
    def equip_skill(identifier: str, payload: SkillEquipRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        player, session = resolve_profile_write(storage, identifier, request)
        equip_player_skill(player, payload.skill_id)
        save_player(storage, player)
        return {"ok": True, "profile": frontend_profile_payload(player, session)}

    @router.post("/{identifier}/skills/unequip")
    def unequip_skill(identifier: str, payload: SkillEquipRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        player, session = resolve_profile_write(storage, identifier, request)
        unequip_player_skill(player, payload.skill_id)
        save_player(storage, player)
        return {"ok": True, "profile": frontend_profile_payload(player, session)}

    @router.post("/{identifier}/skills/use-outside")
    def use_skill_outside_endpoint(identifier: str, payload: SkillUseRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        player, session = resolve_profile_write(storage, identifier, request)
        from services.race_runtime import restriction_error
        denied = restriction_error(player, "skill", payload.skill_id)
        if denied: raise HTTPException(status_code=400, detail=denied)
        if player.get("in_battle") or player.get("active_battle"):
            raise HTTPException(status_code=400, detail="В бою навык применяется через боевые кнопки.")
        try:
            from services.skill_action_runtime import use_outside_battle
            result = use_outside_battle(player, payload.skill_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        sync_player_parameters_for_bots(player)
        save_player(storage, player)
        return {"ok": True, "skill": result, "message": result.get("text"), "profile": frontend_profile_payload(player, session)}

    @router.post("/{identifier}/equipment/equip")
    def equip_inventory_item(identifier: str, payload: EquipItemRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        player, session = resolve_profile_write(storage, identifier, request)
        original_player = deepcopy(player)
        inventory = player.setdefault("inventory", [])
        equipment = player.setdefault("equipment", {})
        item_index = find_inventory_index_for_site_action(inventory, payload.item_id, payload.inventory_index)
        if item_index is None:
            raise HTTPException(status_code=404, detail="Предмет в инвентаре не найден.")
        require_configured_profile_action(inventory[item_index], "equip")
        item = inventory.pop(item_index)
        try:
            validate_equipment_level_requirement(player, item)
            slot_key = compatible_equipment_slot(item, payload.slot_key, equipment)
            from services.effect_runtime_service import blocked_slots as trauma_blocked_slots
            if slot_key in trauma_blocked_slots(player):
                raise HTTPException(status_code=409, detail=trauma_blocked_slots(player)[slot_key])
            previous_item = equipment.get(slot_key)
            if isinstance(previous_item, dict):
                previous_item = prepare_item_for_inventory_from_slot(previous_item, slot_key)
                _add_inventory_item_or_raise(
                    player,
                    previous_item,
                    safe_int(previous_item.get("amount"), 1),
                    "Нельзя заменить экипировку: в инвентаре и доп. слотах нет места для снятого предмета.",
                )
            if is_two_handed_equipment(item):
                blocked_second_weapon = equipment.get("weapon2")
                if isinstance(blocked_second_weapon, dict):
                    blocked_second_weapon = prepare_item_for_inventory_from_slot(blocked_second_weapon, "weapon2")
                    _add_inventory_item_or_raise(
                        player,
                        blocked_second_weapon,
                        safe_int(blocked_second_weapon.get("amount"), 1),
                        "Нельзя надеть двуручное оружие: в инвентаре и доп. слотах нет места для предмета из второго оружейного слота.",
                    )
                    equipment.pop("weapon2", None)
            item["slotKey"] = slot_key
            item.pop("targetSlotKey", None)
            _strip_inventory_storage_markers(item)
            equipment[slot_key] = item
            from services.item_effect_trigger_runtime import trigger as trigger_item_effect
            trigger_item_effect(player, item, "on_equip", context={"slot": slot_key})
            if slot_key == "weapon1":
                unequip_incompatible_weapon2(player, slot_key, fail_on_discard=True)
            recalculate_inventory_overflow(player)
            sync_player_parameters_for_bots(player)
        except HTTPException:
            player.clear()
            player.update(original_player)
            raise
        _achievement_event(player, "equip_item", 1, str(item.get("item_id") or payload.item_id), storage)
        save_player(storage, player)
        return {"ok": True, "profile": frontend_profile_payload(player, session)}

    @router.post("/{identifier}/equipment/unequip")
    def unequip_inventory_item(identifier: str, payload: UnequipItemRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        player, session = resolve_profile_write(storage, identifier, request)
        original_player = deepcopy(player)
        equipment = player.setdefault("equipment", {})
        item = equipment.pop(payload.slot_key, None)
        if not isinstance(item, dict):
            raise HTTPException(status_code=404, detail="В этом слоте нет предмета.")
        try:
            require_configured_profile_action(item, "unequip")
        except HTTPException:
            equipment[payload.slot_key] = item
            raise
        from services.item_effect_trigger_runtime import trigger as trigger_item_effect
        trigger_item_effect(player, item, "on_unequip", context={"slot": payload.slot_key})
        try:
            item = prepare_item_for_inventory_from_slot(item, payload.slot_key)
            _add_inventory_item_or_raise(
                player,
                item,
                safe_int(item.get("amount"), 1),
                "Нельзя снять предмет: в инвентаре и доп. слотах нет места. Предмет остался экипированным.",
            )
            if payload.slot_key == "weapon1":
                unequip_incompatible_weapon2(player, payload.slot_key, fail_on_discard=True)
            recalculate_inventory_overflow(player)
            sync_player_parameters_for_bots(player)
        except HTTPException:
            player.clear()
            player.update(original_player)
            raise
        save_player(storage, player)
        return {"ok": True, "profile": frontend_profile_payload(player, session)}

    @router.post("/{identifier}/promo/redeem")
    def redeem_profile_promo(identifier: str, payload: PromoRedeemRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        player, session = resolve_profile_write(storage, identifier, request)
        code = str(payload.code or "").strip()
        if not code:
            raise HTTPException(status_code=400, detail="Введите промокод.")
        ok, message = redeem_promo_code(storage, str(player.get("game_id")), code)
        if not ok:
            raise HTTPException(status_code=400, detail=message)
        refreshed = storage.get_player_by_game_id(player.get("game_id")) or player
        recalculate_inventory_overflow(refreshed)
        sync_player_parameters_for_bots(refreshed)
        save_player(storage, refreshed)
        return {"ok": True, "message": message, "profile": frontend_profile_payload(refreshed, session)}

    @router.post("/{identifier}/inventory/use")
    def use_inventory_item(identifier: str, payload: UseItemRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        player, session = resolve_profile_write(storage, identifier, request)
        inventory = player.setdefault("inventory", [])
        item_index = find_inventory_index_for_site_action(inventory, payload.item_id, payload.inventory_index)
        if item_index is None:
            raise HTTPException(status_code=404, detail="Предмет в инвентаре не найден.")
        item = inventory[item_index]
        require_configured_profile_action(item, "open" if item.get("can_open") else "use")
        if not is_inventory_item_usable(item):
            raise HTTPException(status_code=400, detail="Этот предмет нельзя использовать напрямую из профиля.")
        item_target = str(item.get("item_id") or item.get("id") or payload.item_id)
        from services.race_runtime import restriction_error as race_restriction_error
        denied = race_restriction_error(player, "item", item_target)
        if denied: raise HTTPException(status_code=400, detail=denied)
        if item.get("can_open"):
            from services.container_item_runtime import open_container
            try:
                opened = open_container(player, item_index)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            recalculate_inventory_overflow(player); sync_player_parameters_for_bots(player)
            _achievement_event(player, "use_item", 1, item_target, storage)
            from services.item_effect_trigger_runtime import trigger as trigger_item_effect
            trigger_item_effect(player, item, "on_open"); trigger_item_effect(player, item, "on_use")
            save_player(storage, player)
            return {"ok": True, "message": str(item.get("open_text") or "Контейнер открыт."), "container": opened, "profile": frontend_profile_payload(player, session)}
        if item.get("grants_npc_helper_id"):
            from services.npc_ally_runtime import grant
            try: helper = grant(player, str(item.get("grants_npc_helper_id")), source=f"item:{item_target}")
            except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc
            if item.get("consume_on_helper_grant", True): remove_inventory_amount_at_index(inventory, item_index, 1)
            recalculate_inventory_overflow(player); sync_player_parameters_for_bots(player)
            _achievement_event(player, "use_item", 1, item_target, storage); save_player(storage, player)
            return {"ok": True, "message": str(item.get("helper_grant_text") or "NPC-помощник присоединился к вам."), "helper": helper, "profile": frontend_profile_payload(player, session)}
        if item.get("opens_access") and str(item.get("access_mode") or "on_use") == "on_use":
            from services.item_access_runtime import grant
            try: access = grant(player, item)
            except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc
            if item.get("access_consumed_on_use", True): remove_inventory_amount_at_index(inventory, item_index, 1)
            recalculate_inventory_overflow(player); sync_player_parameters_for_bots(player)
            from services.item_effect_trigger_runtime import trigger as trigger_item_effect
            trigger_item_effect(player, item, "on_use")
            _achievement_event(player, "use_item", 1, item_target, storage); save_player(storage, player)
            return {"ok": True, "message": str(item.get("access_text_ok") or "Доступ открыт."), "access": access, "profile": frontend_profile_payload(player, session)}
        if is_ammunition_item(item):
            loaded, message = load_ammo_into_quiver(player, item, safe_int(item.get("amount"), 1))
            remove_inventory_amount_at_index(inventory, item_index, loaded)
            recalculate_inventory_overflow(player)
            sync_player_parameters_for_bots(player)
            _achievement_event(player, "use_item", loaded, item_target, storage)
            from services.item_effect_trigger_runtime import trigger as trigger_item_effect
            trigger_item_effect(player, item, "on_use")
            save_player(storage, player)
            return {"ok": True, "message": message, "loadedAmmo": loaded, "profile": frontend_profile_payload(player, session)}
        if is_battle_stimulant_item(item):
            effect = apply_battle_stimulant_inventory_effect(player, item)
            remove_inventory_amount_at_index(inventory, item_index, 1)
            recalculate_inventory_overflow(player)
            sync_player_parameters_for_bots(player)
            _achievement_event(player, "use_item", 1, item_target, storage)
            _achievement_event(player, "gain_effect", 1, str(effect.get("effect_id") or effect.get("id") or "battle_stimulant"), storage)
            from services.item_effect_trigger_runtime import trigger as trigger_item_effect
            trigger_item_effect(player, item, "on_use")
            save_player(storage, player)
            return {"ok": True, "message": "Боевой стимулятор принят. Эффект активен 30 минут.", "effect": effect, "profile": frontend_profile_payload(player, session)}
        if inventory_pocket_spec(item) is not None:
            ok, message = apply_inventory_pocket(player, item)
            if not ok:
                raise HTTPException(status_code=400, detail=message)
            remove_inventory_amount_at_index(inventory, item_index, 1)
            recalculate_inventory_overflow(player)
            sync_player_parameters_for_bots(player)
            _achievement_event(player, "use_item", 1, item_target, storage)
            from services.item_effect_trigger_runtime import trigger as trigger_item_effect
            trigger_item_effect(player, item, "on_use")
            save_player(storage, player)
            return {"ok": True, "message": message, "profile": frontend_profile_payload(player, session)}
        if is_suspicious_potion_item(item):
            effect = suspicious_potion_effect(player)
            add_active_consumable_effect(player, effect)
            remove_inventory_amount_at_index(inventory, item_index, 1)
            recalculate_inventory_overflow(player)
            sync_player_parameters_for_bots(player)
            _achievement_event(player, "use_item", 1, item_target, storage)
            _achievement_event(player, "gain_effect", 1, str(effect.get("effect_id") or effect.get("id") or "suspicious_potion"), storage)
            from services.item_effect_trigger_runtime import trigger as trigger_item_effect
            trigger_item_effect(player, item, "on_use")
            save_player(storage, player)
            return {"ok": True, "message": str(effect.get("message") or "Подозрительное зелье выпито."), "effect": effect, "profile": frontend_profile_payload(player, session)}
        crystal_effect = resource_crystal_effect_from_item(item)
        if crystal_effect is not None:
            add_active_consumable_effect(player, crystal_effect)
            remove_inventory_amount_at_index(inventory, item_index, 1)
            recalculate_inventory_overflow(player)
            sync_player_parameters_for_bots(player)
            _achievement_event(player, "use_item", 1, item_target, storage)
            _achievement_event(player, "gain_effect", 1, str(crystal_effect.get("effect_id") or crystal_effect.get("id") or item_target), storage)
            from services.item_effect_trigger_runtime import trigger as trigger_item_effect
            trigger_item_effect(player, item, "on_use")
            save_player(storage, player)
            minutes = max(1, safe_int(crystal_effect.get("duration_seconds"), 3600) // 60)
            return {"ok": True, "message": f"{crystal_effect.get('name')} использован. Эффект активен {minutes} мин.", "effect": crystal_effect, "profile": frontend_profile_payload(player, session)}
        formula_item = item
        if item.get("use_formula_id"):
            from services.item_formula_runtime import use_result
            formula_item = dict(item)
            formula_item["energy_restore"] = max(0, safe_int(use_result(item, player, item_energy_restore(item)), 0))
        restored_energy = apply_energy_restore(player, formula_item)
        effect = consumable_effect_from_item(item)
        if effect is not None:
            add_active_consumable_effect(player, effect)
        remove_inventory_amount_at_index(inventory, item_index, 1)
        recalculate_inventory_overflow(player)
        sync_player_parameters_for_bots(player)
        _achievement_event(player, "use_item", 1, item_target, storage)
        from services.item_effect_trigger_runtime import trigger as trigger_item_effect
        trigger_item_effect(player, item, "on_use")
        if effect is not None:
            _achievement_event(player, "gain_effect", 1, str(effect.get("effect_id") or effect.get("id") or item_target), storage)
        save_player(storage, player)
        return {"ok": True, "restoredEnergy": restored_energy, "profile": frontend_profile_payload(player, session)}

    @router.post("/{identifier}/inventory/repair")
    def repair_inventory_item_endpoint(identifier: str, payload: UseItemRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        player, session = resolve_profile_write(storage, identifier, request)
        inventory = player.setdefault("inventory", [])
        item_index = find_inventory_index_for_site_action(inventory, payload.item_id, payload.inventory_index)
        if item_index is None:
            raise HTTPException(status_code=404, detail="Предмет в инвентаре не найден.")
        item = inventory[item_index]
        require_configured_profile_action(item, "repair")
        try:
            from services.item_formula_runtime import repair_inventory_item
            result = repair_inventory_item(player, item)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        item_target = str(item.get("item_id") or item.get("id") or payload.item_id)
        _achievement_event(player, "repair_item", 1, item_target, storage)
        recalculate_inventory_overflow(player)
        sync_player_parameters_for_bots(player)
        save_player(storage, player)
        return {"ok": True, "message": f"Предмет отремонтирован. Списано: {result['cost']} медных монет.",
                "repair": result, "profile": frontend_profile_payload(player, session)}

    @router.post("/{identifier}/inventory/profile-action")
    def inventory_profile_action(identifier: str, payload: ProfileItemActionRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        player, session = resolve_profile_write(storage, identifier, request)
        action = str(payload.action or "").strip()
        if action == "storage_remove":
            stored = player.setdefault("personal_storage", [])
            index = payload.inventory_index
            if index is None or index < 0 or index >= len(stored) or not isinstance(stored[index], dict):
                raise HTTPException(status_code=404, detail="Предмет в хранилище не найден.")
            if item_identity(stored[index]) != str(payload.item_id or ""):
                raise HTTPException(status_code=409, detail="Хранилище изменилось. Обновите профиль и повторите действие.")
            original = deepcopy(player)
            item = stored.pop(index)
            amount = max(1, safe_int(item.get("amount"), 1))
            item.pop("storageIndex", None)
            result = add_inventory_item(player, item, amount)
            if result.added < amount:
                player.clear(); player.update(original)
                raise HTTPException(status_code=400, detail="В инвентаре и дополнительных слотах недостаточно места.")
            message = "Предмет забран из хранилища."
        else:
            inventory = player.setdefault("inventory", [])
            index = find_inventory_index_for_site_action(inventory, payload.item_id, payload.inventory_index)
            if index is None:
                raise HTTPException(status_code=404, detail="Предмет в инвентаре не найден.")
            item = inventory[index]
            require_configured_profile_action(item, action)
            if action in {"charge", "discharge"}:
                if not item.get("has_charges"):
                    raise HTTPException(status_code=400, detail="У предмета нет зарядов.")
                maximum = max(1, safe_int(item.get("max_charges"), 1))
                current = max(0, safe_int(item.get("current_charges", item.get("charges")), 0))
                if action == "charge":
                    if current >= maximum:
                        raise HTTPException(status_code=400, detail="Предмет уже полностью заряжен.")
                    cost = max(0, safe_int(item.get("charge_cost"), 0))
                    money_key = "money_copper" if "money_copper" in player else "money"
                    if safe_int(player.get(money_key), 0) < cost:
                        raise HTTPException(status_code=400, detail="Недостаточно денег для зарядки предмета.")
                    player[money_key] = safe_int(player.get(money_key), 0) - cost
                    amount = max(1, safe_int(item.get("charge_amount"), maximum))
                    item["current_charges"] = min(maximum, current + amount)
                    message = f"Предмет заряжен: {item['current_charges']}/{maximum}."
                else:
                    if current <= 0:
                        raise HTTPException(status_code=400, detail="Предмет уже разряжен.")
                    item["current_charges"] = 0
                    message = "Предмет разряжен."
            elif action in {"pouch_store", "pouch_remove"}:
                if action == "pouch_store":
                    used = sum(1 for row in inventory if isinstance(row, dict) and row.get("in_pouch"))
                    capacity = max(0, safe_int(player.get("combat_pouch_capacity"), 5))
                    if not item.get("in_pouch") and used >= capacity:
                        raise HTTPException(status_code=400, detail="В боевом подсумке нет свободного места.")
                    item["in_pouch"] = True
                    message = "Предмет помещён в боевой подсумок."
                else:
                    item["in_pouch"] = False
                    message = "Предмет убран из боевого подсумка."
            elif action == "storage_store":
                original = deepcopy(player)
                amount = max(1, safe_int(item.get("amount"), 1))
                capacity = max(0, safe_int(player.get("personal_storage_capacity"), 20))
                stored = player.setdefault("personal_storage", [])
                if len(stored) >= capacity:
                    raise HTTPException(status_code=400, detail="Персональное хранилище заполнено.")
                moved = inventory.pop(index)
                moved.pop("inventoryIndex", None)
                stored.append(moved)
                if len(stored) > capacity:
                    player.clear(); player.update(original)
                    raise HTTPException(status_code=400, detail="Не удалось безопасно переместить предмет в хранилище.")
                message = f"Предмет помещён в хранилище: ×{amount}."
            else:
                raise HTTPException(status_code=400, detail="Неизвестное действие предмета.")
        recalculate_inventory_overflow(player)
        sync_player_parameters_for_bots(player)
        save_player(storage, player)
        return {"ok": True, "message": message, "profile": frontend_profile_payload(player, session)}

    @router.post("/{identifier}/inventory/craft-operation")
    def craft_operation_endpoint(identifier: str, payload: CraftOperationRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        player, session = resolve_profile_write(storage, identifier, request)
        inventory = player.setdefault("inventory", [])
        item_index = find_inventory_index_for_site_action(inventory, payload.item_id, payload.inventory_index)
        if item_index is None:
            raise HTTPException(status_code=404, detail="Целевой предмет в инвентаре не найден.")
        action_for_operation = {"upgrade": "upgrade", "enchant": "enchant", "repair": "repair", "disassemble": "disassemble", "purify": "disassemble"}.get(payload.operation, payload.operation)
        require_configured_profile_action(inventory[item_index], action_for_operation)
        try:
            from services.craft_operation_runtime import apply
            result = apply(player, payload.operation, payload.rule_id, item_index)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if result.get("ok"):
            _achievement_event(player, f"{payload.operation}_item", 1, payload.item_id, storage)
        recalculate_inventory_overflow(player)
        sync_player_parameters_for_bots(player)
        save_player(storage, player)
        return {"ok": True, "operation": result, "profile": frontend_profile_payload(player, session)}

    @router.post("/{identifier}/inventory/craft-delivery/claim")
    def claim_craft_delivery_endpoint(identifier: str, request: Request) -> dict[str, Any]:
        storage = get_storage()
        player, session = resolve_profile_write(storage, identifier, request)
        from services.craft_result_delivery import claim
        result = claim(player)
        recalculate_inventory_overflow(player)
        sync_player_parameters_for_bots(player)
        save_player(storage, player)
        return {"ok": True, "delivery": result, "profile": frontend_profile_payload(player, session)}

    @router.post("/{identifier}/profile/edit-field")
    def edit_profile_field(identifier: str, payload: EditProfileFieldRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        player, session = resolve_profile_write(storage, identifier, request)
        if str(payload.field).strip().casefold() == "race":
            raise HTTPException(status_code=400, detail="Смена расы выполняется только через предупреждение и отдельное подтверждение.")
        label = apply_profile_field_edit(player, payload.field, payload.value, storage=storage)
        sync_player_parameters_for_bots(player)
        save_player(storage, player)
        return {"ok": True, "field": str(payload.field), "value": label, "profile": frontend_profile_payload(player, session)}

    @router.post("/{identifier}/inventory/sell")
    def sell_inventory_item(identifier: str, payload: SellItemRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        player, session = resolve_profile_write(storage, identifier, request)
        if not is_profile_market_sell_enabled(player):
            raise HTTPException(status_code=400, detail="Продажа через профиль доступна только в разделе продажи на рынке.")
        inventory = player.setdefault("inventory", [])
        item_index = find_inventory_index_for_site_action(inventory, payload.item_id, payload.inventory_index)
        if item_index is None:
            raise HTTPException(status_code=404, detail="Предмет в инвентаре не найден.")
        require_configured_profile_action(inventory[item_index], "sell")
        sold_item_id=str(inventory[item_index].get("item_id") or inventory[item_index].get("id") or payload.item_id)
        result = sell_item_from_profile(storage, player, payload.item_id, payload.amount, payload.inventory_index)
        if "Продано:" not in result.text:
            raise HTTPException(status_code=400, detail=result.text)
        refreshed = storage.get_player_by_game_id(player.get("game_id")) or player
        from services.item_access_runtime import revoke_for_item_action
        revoke_for_item_action(refreshed,sold_item_id,"sell")
        recalculate_inventory_overflow(refreshed)
        sync_player_parameters_for_bots(refreshed)
        save_player(storage, refreshed)
        return {"ok": True, "message": result.text, "profile": frontend_profile_payload(refreshed, session)}


    @router.post("/{identifier}/inventory/drop")
    def drop_inventory_item(identifier: str, payload: DropItemRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        player, session = resolve_profile_write(storage, identifier, request)
        inventory = player.setdefault("inventory", [])
        item_index = find_inventory_index_for_site_action(inventory, payload.item_id, payload.inventory_index)
        if item_index is None:
            raise HTTPException(status_code=404, detail="Предмет в инвентаре не найден.")
        item = inventory[item_index]
        forbidden = inventory_drop_error(item)
        if forbidden:
            raise HTTPException(status_code=400, detail=forbidden)
        amount = max(1, safe_int(item.get("amount"), 1))
        drop_amount = min(amount, max(1, safe_int(payload.amount, 1)))
        if amount > drop_amount:
            item["amount"] = amount - drop_amount
        else:
            inventory.pop(item_index)
        from services.item_effect_trigger_runtime import trigger as trigger_item_effect
        trigger_item_effect(player, item, "on_drop", context={"item_count": drop_amount})
        from services.item_access_runtime import revoke_for_item_action
        revoke_for_item_action(player,str(item.get("item_id") or item.get("id") or payload.item_id),"drop")
        recalculate_inventory_overflow(player)
        sync_player_parameters_for_bots(player)
        save_player(storage, player)
        return {"ok": True, "profile": frontend_profile_payload(player, session)}

    @router.get("/{identifier}/courier/search")
    def courier_search(identifier: str, request: Request, q: str = "") -> dict[str, Any]:
        storage = get_storage()
        player, _session = resolve_profile_read(storage, identifier, request)
        own_id = str(player.get("game_id") or player.get("id") or "")
        results = [
            entry
            for entry in courier_search_players(storage, q)
            if str(entry.get("gameId")) != own_id
        ]
        return {"ok": True, "players": results}

    @router.post("/{identifier}/courier/send")
    def courier_send(identifier: str, payload: CourierSendRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        player, session = resolve_profile_write(storage, identifier, request)
        item_requests = [
            {
                "item_id": item.item_id,
                "inventory_index": item.inventory_index,
                "amount": item.amount,
            }
            for item in payload.items
        ]
        try:
            result = create_courier_transfer(
                storage,
                player,
                payload.receiver,
                item_requests,
                payload.coins,
                payload.letter,
            )
        except CourierError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        from services.item_access_runtime import revoke_for_item_action
        for request_item in item_requests:revoke_for_item_action(player,str(request_item.get("item_id") or ""),"transfer")
        # Посылка уже оформлена и СОХРАНЕНА внутри create_courier_transfer
        # (списание durable до постановки в очередь). Повторное сохранение
        # синх-параметров для ботов не должно делать запрос повторяемым: при сбое
        # клиент создал бы вторую платную посылку. Параметры пересчитаются при
        # следующем действии игрока.
        sync_player_parameters_for_bots(player)
        try:
            save_player(storage, player)
        except Exception:
            pass
        return {
            "ok": True,
            "message": result["message"],
            "profile": frontend_profile_payload(player, session),
        }

    return router
