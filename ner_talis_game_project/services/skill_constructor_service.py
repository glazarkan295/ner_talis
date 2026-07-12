"""Конструктор навыков V2 (ТЗ §7) — авторская часть.

Здесь админ задаёт ОПРЕДЕЛЕНИЯ навыков/умений (шаблоны): ветвь/путь, тип
(активный/пассивный), ресурс и стоимость, откат, тип урона и формула, цель,
требования к оружию, порог открытия пути и модификаторы. Это слой данных +
валидация; рантайм активных навыков игрока — services/active_skill_service.py
(каталог data/active_skills_registry.json, выбор у Распорядительного камня,
расход ресурса, кулдауны, пассивные бонусы).

Хранение — генерик EntityStore (data/skill_constructor.json). Аудит и права — в
роутере (admin_skills_api) через admin_operation. Существующие навыки каталога
заводятся как опубликованные записи через constructor_import.import_skills.
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore

# --- Статусы (как у остальных конструкторов) --------------------------------
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

# --- Справочники (ТЗ §7) ----------------------------------------------------
SKILL_TYPES = ("active", "passive")  # активный / пассивный

# Ветви развития (как у Распорядительного камня); neutral — стартовые навыки.
BRANCHES = ("neutral", "spirit", "mana")

# Пути внутри ветвей (active_skill_service.SPIRIT_PATHS / MANA_PATHS) + none.
SPIRIT_PATHS = ("sword", "dagger", "axe", "hammer", "bow", "shield", "crossbow")
MANA_PATHS = ("fire", "water", "earth", "air", "support", "death", "life")
PATHS = ("none",) + SPIRIT_PATHS + MANA_PATHS
PATHS_BY_BRANCH = {"neutral": ("none",), "spirit": SPIRIT_PATHS, "mana": MANA_PATHS}

RESOURCE_TYPES = ("none", "spirit", "mana", "energy", "hp")  # ресурс расхода
DAMAGE_TYPES = ("none", "physical", "magic", "mixed")
TARGET_MODES = (  # цель применения
    "self", "single_enemy", "all_enemies", "ally", "all_allies", "passive",
)
WEAPON_REQUIREMENTS = (  # требуемое оружие (active_skill_service токены)
    "any", "sword", "dagger", "axe", "hammer", "bow", "shield", "crossbow",
    "staff", "magic_book",
)

# Мягкие границы для балансных предупреждений.
MAX_RESOURCE_COST = 500
MAX_COOLDOWN_TURNS = 30
MAX_PATH_THRESHOLD = 10000

_HTML_RE = re.compile(r"<[^>]+>")

_store = EntityStore(
    env_var="SKILL_CONSTRUCTOR_PATH",
    default_rel="data/skill_constructor.json",
    statuses=STATUSES,
    transitions=TRANSITIONS,
    initial_status=STATUS_DRAFT,
)


def store() -> EntityStore:
    return _store


def _has_markup(value: str) -> bool:
    low = value.lower()
    return "<script" in low or bool(_HTML_RE.search(value))


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _weapon_list(data: dict[str, Any]) -> list[str]:
    raw = data.get("weapon_requirements")
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item or "").strip()]
    return []


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    """Проверка определения навыка перед публикацией (ТЗ §7)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not str(data.get("name") or "").strip():
        errors.append("Не заполнено название навыка.")

    skill_type = str(data.get("skill_type") or "active").strip()
    if skill_type and skill_type not in SKILL_TYPES:
        errors.append(f"Неизвестный тип навыка: {skill_type}.")
    is_passive = skill_type == "passive"

    branch = str(data.get("branch") or "").strip()
    if branch and branch not in BRANCHES:
        errors.append(f"Неизвестная ветвь: {branch}.")
    path = str(data.get("path") or "").strip()
    if path and path not in PATHS:
        errors.append(f"Неизвестный путь: {path}.")
    # Путь должен принадлежать выбранной ветви.
    if branch in PATHS_BY_BRANCH and path and path not in PATHS_BY_BRANCH[branch] and path != "none":
        errors.append(f"Путь «{path}» не относится к ветви «{branch}».")

    resource_type = str(data.get("resource_type") or "none").strip()
    if resource_type and resource_type not in RESOURCE_TYPES:
        errors.append(f"Неизвестный тип ресурса: {resource_type}.")
    damage_type = str(data.get("damage_type") or "none").strip()
    if damage_type and damage_type not in DAMAGE_TYPES:
        errors.append(f"Неизвестный тип урона: {damage_type}.")
    target_mode = str(data.get("target_mode") or "").strip()
    if target_mode and target_mode not in TARGET_MODES:
        errors.append(f"Неизвестный режим цели: {target_mode}.")

    for token in _weapon_list(data):
        if token not in WEAPON_REQUIREMENTS:
            errors.append(f"Неизвестное требование к оружию: {token}.")

    # Числовые поля — неотрицательные.
    cost = _num(data.get("resource_cost"))
    if data.get("resource_cost") not in (None, "") and cost is None:
        errors.append("Стоимость ресурса — не число.")
    elif cost is not None and cost < 0:
        errors.append("Стоимость ресурса не может быть отрицательной.")
    cooldown = _num(data.get("cooldown_turns"))
    if data.get("cooldown_turns") not in (None, "") and cooldown is None:
        errors.append("Откат — не число.")
    elif cooldown is not None and cooldown < 0:
        errors.append("Откат не может быть отрицательным.")
    threshold = _num(data.get("unlock_path_level"))
    if data.get("unlock_path_level") not in (None, "") and threshold is None:
        errors.append("Порог открытия — не число.")
    elif threshold is not None and threshold < 0:
        errors.append("Порог открытия не может быть отрицательным.")
    idx = _num(data.get("choice_index"))
    if data.get("choice_index") not in (None, "") and idx is None:
        errors.append("Индекс выбора — не число.")
    elif idx is not None and idx < 0:
        errors.append("Индекс выбора не может быть отрицательным.")
    learn_cost = _num(data.get("learn_cost_skill_points"))
    if data.get("learn_cost_skill_points") not in (None, "") and (learn_cost is None or learn_cost < 0):
        errors.append("Цена изучения должна быть неотрицательным числом.")
    source_type = str(data.get("source_type") or "standard")
    source_fields = {"item": "linked_item_id", "mob": "linked_mob_id", "achievement": "linked_achievement_id"}
    if source_type in source_fields and not str(data.get(source_fields[source_type]) or "").strip():
        errors.append(f"Для источника «{source_type}» не выбран связанный объект.")
    if (data.get("special") or source_type == "special") and data.get("hidden") and not str(data.get("unlock_condition") or "").strip():
        errors.append("Скрытый особый навык должен иметь условие открытия.")
    if data.get("ammo_enabled") and not str(data.get("ammo_item_id") or "").strip():
        errors.append("Для навыка с боеприпасами не выбран предмет боеприпаса.")
    if is_passive and data.get("passive_slot_cost") not in (None, "") and (_num(data.get("passive_slot_cost")) or 0) < 1:
        errors.append("Пассивный навык должен занимать минимум один пассивный слот.")

    # Модификаторы — список словарей с названием.
    modifiers = data.get("modifiers")
    if modifiers not in (None, ""):
        if not isinstance(modifiers, list):
            errors.append("Модификаторы должны быть списком.")
        else:
            for mod in modifiers:
                name = mod.get("name") if isinstance(mod, dict) else mod
                if not str(name or "").strip():
                    errors.append("У модификатора не заполнено название.")
                    break

    # Безопасность текстов (§7): без HTML/скриптов.
    text_fields = [str(data.get(k) or "") for k in ("name", "short_description", "description", "effect", "player_text")]
    if isinstance(modifiers, list):
        for mod in modifiers:
            if isinstance(mod, dict):
                text_fields.extend(str(mod.get(k) or "") for k in ("name", "effect", "description"))
    for value in text_fields:
        if value and _has_markup(value):
            errors.append("В текстах навыка недопустима разметка/HTML.")
            break

    # --- Балансные предупреждения (не блокируют публикацию) -----------------
    if is_passive:
        if cost is not None and cost > 0:
            warnings.append("Пассивный навык со стоимостью ресурса — обычно расход не нужен.")
        if cooldown is not None and cooldown > 0:
            warnings.append("Пассивный навык с откатом — обычно откат не нужен.")
        if target_mode and target_mode != "passive":
            warnings.append("Для пассивного навыка ожидается цель «пассивно».")
    else:
        if resource_type != "none" and (cost is None or cost <= 0):
            warnings.append("Активный навык с ресурсом, но без стоимости ресурса.")
        if not str(data.get("description") or data.get("effect") or "").strip():
            warnings.append("У активного навыка не заполнено описание эффекта.")
    if cost is not None and cost > MAX_RESOURCE_COST:
        warnings.append(f"Очень высокая стоимость ресурса (> {MAX_RESOURCE_COST}).")
    if cooldown is not None and cooldown > MAX_COOLDOWN_TURNS:
        warnings.append(f"Очень длинный откат (> {MAX_COOLDOWN_TURNS} ходов).")
    if threshold is not None and threshold > MAX_PATH_THRESHOLD:
        warnings.append(f"Порог открытия выше максимума пути ({MAX_PATH_THRESHOLD}).")

    from services.formula_runtime import validate_references
    errors.extend(validate_references(data, (
        "damage_formula_id", "use_cost_formula_id", "learn_cost_formula_id",
        "upgrade_cost_formula_id", "level_power_formula_id", "hp_formula_id",
        "mana_formula_id", "spirit_formula_id", "energy_formula_id",
    )))
    for raw in list(data.get("apply_effect_ids") or []) + list(data.get("remove_effect_ids") or []):
        effect_id = str(raw or "")
        if effect_id:
            from services.effect_constructor_service import published_definition
            if not published_definition(effect_id):
                errors.append(f"Эффект навыка «{effect_id}» не опубликован.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
