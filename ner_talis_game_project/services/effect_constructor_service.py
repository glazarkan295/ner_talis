"""Конструктор эффектов/зон/проклятий V2 (ТЗ «свойства, эффекты и зоны»).

По рекомендации ТЗ §9 — не 82 отдельные системы, а несколько универсальных
типов (stat_modifier, resource_regeneration, max_resource_modifier,
periodic_damage, control_effect, damage_response, absorb_effect, aura_effect,
summon_effect, curse_effect, zone_effect, zone_protection, item_lifecycle) плюс
параметрические модификаторы (крит/точность/защита и т.п.).

Главное правило UX: игроку показываем только player_text (без формул).
Формулы/коэффициенты живут в admin_description и числовых полях.

Слой данных + валидация. Хранение — EntityStore (data/effect_constructor.json).
Аудит/права — в роутере (admin_effect_api). Реальное применение эффектов уже
делает движок (derived_stats/pve_battle/...); конструктор задаёт определения —
их подключение к движку как data-driven источника — runtime на вырост.
"""

from __future__ import annotations

from typing import Any

from services.admin_entity_store import EntityStore

# --- Статусы ----------------------------------------------------------------
STATUS_DRAFT = "draft"
STATUS_REVIEW = "review"
STATUS_READY = "ready"
STATUS_PUBLISHED = "published"
STATUS_DISABLED = "disabled"
STATUS_ARCHIVE = "archive"
STATUS_ERROR = "error"

STATUSES = (STATUS_DRAFT, STATUS_REVIEW, STATUS_READY, STATUS_PUBLISHED, STATUS_DISABLED, STATUS_ARCHIVE, STATUS_ERROR)
STATUS_LABELS = {
    STATUS_DRAFT: "Черновик", STATUS_REVIEW: "На проверке", STATUS_READY: "Готов к публикации",
    STATUS_PUBLISHED: "Опубликован", STATUS_DISABLED: "Отключён", STATUS_ARCHIVE: "Архив",
    STATUS_ERROR: "Ошибка проверки",
}
TRANSITIONS: dict[str, set[str]] = {
    STATUS_DRAFT: {STATUS_REVIEW, STATUS_READY, STATUS_ARCHIVE, STATUS_ERROR},
    STATUS_REVIEW: {STATUS_DRAFT, STATUS_READY, STATUS_ARCHIVE, STATUS_ERROR},
    STATUS_READY: {STATUS_DRAFT, STATUS_PUBLISHED, STATUS_ARCHIVE, STATUS_ERROR},
    STATUS_PUBLISHED: {STATUS_DISABLED, STATUS_ARCHIVE},
    STATUS_DISABLED: {STATUS_PUBLISHED, STATUS_DRAFT, STATUS_ARCHIVE},
    STATUS_ARCHIVE: {STATUS_DRAFT},
    STATUS_ERROR: {STATUS_DRAFT, STATUS_REVIEW, STATUS_ARCHIVE},
}

# --- Справочники (ТЗ §1.1, §9 + расширение §2) ------------------------------
EFFECT_TYPES = (
    "stat_modifier", "resource_regeneration", "max_resource_modifier",
    "periodic_damage", "control_effect", "damage_response", "absorb_effect",
    "aura_effect", "summon_effect", "curse_effect", "zone_effect",
    "zone_protection", "item_lifecycle",
    "crit_damage_modifier", "crit_chance_modifier", "accuracy_modifier",
    "dodge_modifier", "physical_defense_modifier", "magic_defense_modifier",
    "inventory_slot_bonus", "bonus_action_modifier", "encounter_chance_modifier",
    # Расширение (ТЗ §2.3).
    "resource_modifier", "instant_heal", "instant_resource_restore",
    "damage_modifier", "damage_taken_modifier", "defense_modifier", "shield",
    "barrier", "action_block", "slot_block", "cooldown_modifier",
    "event_chance_modifier", "loot_modifier", "craft_modifier", "trade_modifier",
    "quest_modifier", "achievement_passive", "reputation_modifier",
    "hidden_reputation_modifier", "mark_effect", "addiction_effect",
    "tolerance_effect", "item_charge_effect", "item_durability_effect",
    "item_binding_effect", "conditional_unlock", "notification_effect",
    "scripted_effect",
)
# Категории эффектов (ТЗ §2.2).
EFFECT_CATEGORIES = (
    "combat", "resource", "stat", "defense", "damage", "control", "trauma",
    "curse", "zone", "zone_protection", "craft", "alchemy", "gathering",
    "fishing", "trade", "quest", "achievement", "reputation",
    "hidden_reputation", "mark", "addiction", "tolerance", "social",
    "item_lifecycle", "summon", "boss_phase", "technical", "custom",
)
SOURCE_TYPES = (
    "item", "equipped_item", "inventory_item", "special_slot_item", "pouch_item",
    "consumable", "potion", "food", "skill", "passive_skill", "mob_skill",
    "mob_trait", "boss_phase", "curse", "trauma", "zone", "location", "city",
    "region", "world_event", "quest", "achievement", "reputation",
    "hidden_reputation", "mark", "addiction", "tolerance", "admin", "system",
    "moderation", "home", "guild", "faction", "mob", "trap", "event", "custom",
)
TARGETS = ("self", "wearer", "enemy", "ally", "party", "raid", "all_battle", "random")
# Полный список целей (ТЗ §2.5) — поле target_type.
TARGET_TYPES = (
    "self", "enemy", "ally", "party", "raid", "all_enemies", "all_allies",
    "all_participants", "random_enemy", "random_ally", "player", "mob", "boss",
    "location", "city", "region", "item", "skill", "service", "inventory_slot",
    "weapon_slot_1", "weapon_slot_2", "pouch", "home", "quest", "faction", "custom",
)
ACTIVE_WHEN = (
    "equipped", "in_inventory", "in_battle", "on_enter_location", "on_death",
    "on_attack", "on_receive_damage", "on_deal_damage", "always",
    # Расширение (ТЗ §2.6).
    "in_special_slot", "in_pouch", "consumed", "activated", "outside_battle",
    "in_city", "in_region", "in_zone", "during_world_event", "during_quest",
    "after_quest_completed", "after_achievement_unlocked", "while_mark_active",
    "while_addiction_active", "while_tolerance_active",
    "while_hidden_reputation_stage_active", "on_low_hp", "after_death",
    "on_use_skill", "on_use_item", "on_trade", "on_craft", "on_gather",
    "on_fishing", "on_rest", "on_home_rest", "on_admin_apply", "custom_condition",
)
# Триггеры (ТЗ §2.7).
TRIGGER_TYPES = (
    "manual", "automatic", "on_apply", "on_remove", "on_tick", "each_turn",
    "each_action", "each_search", "each_minute", "each_hour", "battle_start",
    "turn_start", "turn_end", "before_attack", "after_attack", "before_damage",
    "after_damage", "before_heal", "after_heal", "on_resource_change",
    "on_reputation_change", "on_hidden_reputation_change", "on_mark_stage_change",
    "on_addiction_stage_change", "on_tolerance_stage_change", "on_level_up",
    "on_quest_start", "on_quest_complete", "on_quest_fail", "on_item_equip",
    "on_item_unequip", "on_item_consume", "on_location_enter", "on_location_leave",
    "on_service_use", "custom",
)
# Способы длительности (ТЗ §2.8).
DURATION_MODES = (
    "instant", "turns", "seconds", "minutes", "hours", "days", "until_battle_end",
    "until_location_leave", "until_zone_leave", "until_item_removed",
    "while_condition_true", "permanent", "until_cleansed", "until_stage_changed",
    "until_admin_remove", "custom",
)
STACK_RULES = (
    "none", "refresh", "strongest_only", "newest_only", "oldest_only",
    "stack_limited", "additive_limited", "multiplicative_limited", "unique_only",
    "per_source", "per_tag", "replace_same_source", "separate_instances", "custom",
)
# Видимость игроку (ТЗ §2.10 / §6.8).
VISIBILITY_MODES = (
    "hidden", "name_only", "name_and_description", "stage_only", "exact_values",
    "warning_only", "after_triggered",
)
RESOURCES = ("hp", "mana", "spirit")
STATS = ("strength", "wisdom", "endurance", "agility", "perception", "intelligence")
CONTROL_KINDS = ("stun", "confusion", "panic", "freeze", "root")
CLEANSE_TAGS = (
    "poison", "fire", "burn", "bleed", "curse", "control", "cold", "freeze",
    "negative_effect", "spirit",
)
ZONE_ELEMENTS = (
    "fire", "water", "frost", "earth", "wind", "spirit", "curse", "holy",
    "shadow", "chaos", "ancient_magic",
)
# Типы, для которых периодический/ответный урон НЕ должен запускать цепочки
# (ТЗ §1.2): для них can_trigger_effects/can_be_reflected должны быть false.
_NO_CHAIN_TYPES = {"periodic_damage", "damage_response", "aura_effect"}
# Мягкий потолок периодического урона за тик (% max HP) — выше → warning.
_PERIODIC_DAMAGE_SOFT_CAP = 6.0
_CRIT_CHANCE_HARD_CAP = 49.0

_store = EntityStore(
    env_var="EFFECT_CONSTRUCTOR_PATH",
    default_rel="data/effect_constructor.json",
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


def _truthy(value: Any) -> bool:
    return bool(value) and str(value).strip().lower() not in {"0", "false", "no", ""}


def where_used(effect_id: str) -> list[dict[str, Any]]:
    """Где используется эффект (ТЗ §12): мобы/зоны/события, ссылающиеся на него.

    Сканирует конструктор мира (world_content_registry): mob_effect.effect_id,
    защита зон location_zone.protections[].effect_id и поле effect у событий.
    Возвращает [{kind, id, name}]. Реестр недоступен → пустой список."""
    eid = str(effect_id or "").strip()
    if not eid:
        return []
    used: list[dict[str, Any]] = []
    try:
        from services import world_content_registry as wcr
    except Exception:
        return []

    def _name(env: dict[str, Any]) -> str:
        data = env.get("data") or {}
        return str(data.get("name") or env.get("id"))

    for env in wcr.list_content(wcr.KIND_MOB_EFFECT):
        if str((env.get("data") or {}).get("effect_id") or "") == eid:
            used.append({"kind": "mob_effect", "id": env.get("id"), "name": _name(env)})
    for env in wcr.list_content(wcr.KIND_LOCATION_ZONE):
        protections = (env.get("data") or {}).get("protections")
        if isinstance(protections, list) and any(str((p or {}).get("effect_id") or "") == eid for p in protections if isinstance(p, dict)):
            used.append({"kind": "location_zone", "id": env.get("id"), "name": _name(env)})
    for env in wcr.list_content(wcr.KIND_EVENT):
        if str((env.get("data") or {}).get("effect") or "") == eid:
            used.append({"kind": "event", "id": env.get("id"), "name": _name(env)})

    # Источник-достижение (ТЗ 09 §17.2): достижения, выдающие этот эффект.
    try:
        from services import achievement_service
        for env in achievement_service.store().list():
            data = env.get("data") or {}
            effects = data.get("effects")
            in_list = isinstance(effects, list) and any(_effect_ref(e) == eid for e in effects)
            in_rewards = isinstance(data.get("rewards"), list) and any(
                isinstance(r, dict) and str(r.get("type") or "") == "effect"
                and str(r.get("effect_id") or "") == eid for r in data["rewards"])
            if in_list or in_rewards:
                used.append({"kind": "achievement", "id": env.get("id"),
                             "name": str(data.get("name") or env.get("id"))})
    except Exception:
        pass
    return used


def _effect_ref(entry: Any) -> str:
    """Ссылка на эффект из элемента списка effects: id-строка или {effect_id}."""
    if isinstance(entry, dict):
        return str(entry.get("effect_id") or entry.get("id") or "").strip()
    return str(entry or "").strip()


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    """Проверка определения эффекта (ТЗ §1.1, §1.2, баланс)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not str(data.get("effect_name") or "").strip():
        errors.append("Не заполнено название эффекта (для админки).")
    if _truthy(data.get("show_to_player")) and not str(data.get("player_text") or "").strip():
        errors.append("Эффект показывается игроку, но нет текста для игрока (player_text).")

    etype = str(data.get("effect_type") or "").strip()
    if not etype:
        errors.append("Не выбран тип эффекта.")
    elif etype not in EFFECT_TYPES:
        errors.append(f"Неизвестный тип эффекта: {etype}.")

    source = str(data.get("source_type") or "").strip()
    if source and source not in SOURCE_TYPES:
        errors.append(f"Неизвестный источник: {source}.")
    target = str(data.get("target") or "").strip()
    if target and target not in TARGETS:
        errors.append(f"Неизвестная цель: {target}.")
    stack_rule = str(data.get("stack_rule") or "").strip()
    if stack_rule and stack_rule not in STACK_RULES:
        errors.append(f"Неизвестное правило стака: {stack_rule}.")

    chance = _num(data.get("apply_chance_percent"))
    if chance is not None and (chance < 0 or chance > 100):
        errors.append("Шанс наложения должен быть 0–100.")
    for key in ("duration_turns", "duration_seconds", "max_stacks"):
        value = _num(data.get(key))
        if value is not None and value < 0:
            errors.append(f"Поле «{key}» не может быть отрицательным.")

    # Тип-специфичные проверки.
    if etype == "stat_modifier" and str(data.get("stat") or "").strip() not in STATS:
        errors.append("stat_modifier требует корректный stat.")
    if etype in ("max_resource_modifier", "resource_regeneration", "absorb_effect"):
        if str(data.get("resource") or "").strip() not in RESOURCES:
            errors.append(f"{etype} требует resource (hp/mana/spirit).")
    if etype == "control_effect" and str(data.get("control_kind") or "").strip() not in CONTROL_KINDS:
        errors.append("control_effect требует корректный control_kind.")
    if etype == "zone_effect" and str(data.get("zone_element") or "").strip() not in ZONE_ELEMENTS:
        errors.append("zone_effect требует корректный zone_element.")
    if etype == "crit_chance_modifier":
        value = _num(data.get("value_percent"))
        if value is not None and value > _CRIT_CHANCE_HARD_CAP:
            warnings.append(f"Бонус шанса крита выше потолка {_CRIT_CHANCE_HARD_CAP}%.")

    if etype == "periodic_damage":
        pct = _num(data.get("percent_max_hp_damage"))
        if pct is not None and pct > _PERIODIC_DAMAGE_SOFT_CAP:
            warnings.append("Периодический урон за тик выше рекомендуемого предела (~6% max HP).")

    # Анти-цепочки (ТЗ §1.2): для периодического/ответного/аурного урона
    # can_trigger_effects и can_be_reflected должны быть false.
    if etype in _NO_CHAIN_TYPES:
        if _truthy(data.get("can_trigger_effects")):
            warnings.append("Для этого типа can_trigger_effects должно быть выключено (защита от бесконечных цепочек).")
        if _truthy(data.get("can_be_reflected")):
            warnings.append("Для этого типа can_be_reflected должно быть выключено.")

    # Расширение конструктора (ТЗ §2): новые справочные поля — мягкая проверка.
    category = str(data.get("effect_category") or "").strip()
    if category and category not in EFFECT_CATEGORIES:
        warnings.append(f"Категория «{category}» не из стандартного списка.")
    target_type = str(data.get("target_type") or "").strip()
    if target_type and target_type not in TARGET_TYPES:
        warnings.append(f"Цель «{target_type}» не из стандартного списка.")
    active_when = str(data.get("active_when") or "").strip()
    if active_when and active_when not in ACTIVE_WHEN:
        warnings.append(f"Режим «когда работает» «{active_when}» не из списка.")
    trigger_type = str(data.get("trigger_type") or "").strip()
    if trigger_type and trigger_type not in TRIGGER_TYPES:
        warnings.append(f"Триггер «{trigger_type}» не из списка.")
    duration_mode = str(data.get("duration_mode") or "").strip()
    if duration_mode and duration_mode not in DURATION_MODES:
        warnings.append(f"Способ длительности «{duration_mode}» не из списка.")
    visibility = str(data.get("visibility_mode") or "").strip()
    if visibility and visibility not in VISIBILITY_MODES:
        warnings.append(f"Режим видимости «{visibility}» не из списка.")
    priority = _num(data.get("priority"))
    if data.get("priority") not in (None, "") and priority is None:
        errors.append("Приоритет должен быть числом.")
    # §8.3: постоянный эффект должен иметь способ снятия/пересчёта.
    if duration_mode == "permanent" and not (
        _truthy(data.get("can_be_cleansed")) or _truthy(data.get("can_be_dispelled"))
        or _truthy(data.get("recalculate_on_hidden_reputation_change"))
        or str(data.get("linked_hidden_reputation_id") or "").strip()
    ):
        warnings.append("Постоянный эффект без способа снятия или условия пересчёта (ТЗ §8.3).")
    # §8.3: метка должна ссылаться на скрытую репутацию.
    if etype == "mark_effect" and not str(data.get("linked_hidden_reputation_id") or "").strip():
        warnings.append("Эффект-метка должен иметь linked_hidden_reputation_id (ТЗ §8.3).")

    for key in ("effect_name", "player_name", "player_text", "admin_description"):
        value = str(data.get(key) or "").strip()
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
