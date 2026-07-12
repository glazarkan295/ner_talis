"""Конструктор ремесла V2 (ТЗ «импорт ремесла») — авторская часть.

Здесь админ задаёт РЕЦЕПТЫ ремесла: мастерская/раздел, результат, ингредиенты,
время, шансы успеха/качества/провала, чертёж, скрытость. Это слой данных +
валидация; опубликованные записи читает services/crafting_service.py и они
перекрывают одноимённые рецепты из data/crafting_recipes.json. Хранение — EntityStore
(data/recipe_constructor.json). Аудит и права (recipe.*) — в роутере
admin_recipes_api. Существующие рецепты заводятся constructor_import.import_recipes.
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

# --- Справочники (ТЗ §3) ----------------------------------------------------
# Мастерские (коды как в data/crafting_recipes.json + чародейская на вырост).
WORKSHOPS = ("smeltery", "forge", "leatherwork", "alchemy", "jewelry", "enchanting")
WORKSHOP_LABELS = {
    "smeltery": "Плавильня", "forge": "Кузница", "leatherwork": "Кожевенная мастерская",
    "alchemy": "Алхимическая мастерская", "jewelry": "Ювелирная мастерская",
    "enchanting": "Чародейская мастерская",
}

# Типы рецептов (ТЗ 13 §5.7).
RECIPE_TYPES = (
    "create_item", "create_material", "smelt", "process", "alchemy", "cooking",
    "smithing", "armor", "weapon", "potion", "poison", "pill", "artifact",
    "jewelry", "enchant", "upgrade", "repair", "disassemble", "purify",
    "combine", "create_blueprint", "learn_blueprint", "quest", "event",
)
RECIPE_TYPE_LABELS = {
    "create_item": "Создание предмета", "create_material": "Создание материала",
    "smelt": "Плавка", "process": "Переработка", "alchemy": "Алхимия",
    "cooking": "Кулинария", "smithing": "Кузнечное изделие", "armor": "Броня",
    "weapon": "Оружие", "potion": "Зелье", "poison": "Яд", "pill": "Пилюля",
    "artifact": "Артефакт", "jewelry": "Ювелирное изделие", "enchant": "Зачарование",
    "upgrade": "Улучшение", "repair": "Ремонт", "disassemble": "Разборка",
    "purify": "Очищение", "combine": "Объединение", "create_blueprint": "Создание чертежа",
    "learn_blueprint": "Изучение чертежа", "quest": "Квестовое", "event": "Событийное",
}

# Роли предметов в рецепте (ТЗ 13 §5.8).
MATERIAL_ROLES = (
    "main", "secondary", "rare", "catalyst", "reagent", "fuel", "tool",
    "blueprint", "mold", "blank", "intermediate", "result", "byproduct",
    "upgrade_target", "enchant_target", "disassemble_target", "repair_target",
    "purify_target", "process_consumable", "container", "recipe_key", "reward",
)
MATERIAL_ROLE_LABELS = {
    "main": "Основной материал", "secondary": "Дополнительный материал",
    "rare": "Редкий материал", "catalyst": "Катализатор", "reagent": "Реагент",
    "fuel": "Топливо", "tool": "Инструмент", "blueprint": "Чертёж", "mold": "Форма",
    "blank": "Заготовка", "intermediate": "Промежуточный компонент", "result": "Результат",
    "byproduct": "Побочный результат", "upgrade_target": "Улучшаемый предмет",
    "enchant_target": "Для зачарования", "disassemble_target": "Для разборки",
    "repair_target": "Для ремонта", "purify_target": "Для очищения",
    "process_consumable": "Расходник процесса", "container": "Контейнер",
    "recipe_key": "Ключ доступа", "reward": "Награда за ремесло",
}

INGREDIENT_TYPES = (
    "item", "resource", "material", "ore", "ingot", "plate", "leather", "fabric",
    "alchemy", "herb", "mushroom", "root", "berry", "meat", "fish", "catch",
    "gem", "catalyst", "reagent", "fuel", "tool", "blueprint", "recipe", "blank",
    "target_item", "quest_item", "special", "currency", "effect", "stored_resource",
)
TOOL_TYPES = ("hammer", "tongs", "knife", "needle", "pot", "mortar", "alchemy_kit", "jewelry_kit", "enchanting_tool", "repair_kit", "disassembly_kit", "mold", "furnace", "campfire", "bait", "fishing_rod", "special", "quest")
RESULT_DELIVERY_MODES = ("inventory", "overload", "delivery", "partial", "reject")
FORMULA_FIELDS = (
    "result_formula_id", "time_formula_id", "cost_formula_id", "exp_formula_id",
    "energy_formula_id", "success_formula_id", "critical_formula_id", "fail_formula_id",
    "quality_formula_id", "material_loss_formula_id", "tool_durability_formula_id",
    "repair_formula_id", "upgrade_formula_id", "enchant_formula_id", "purify_formula_id",
    "curse_risk_formula_id", "break_risk_formula_id", "byproduct_formula_id",
)

_HTML_RE = re.compile(r"<[^>]+>")

_store = EntityStore(
    env_var="RECIPE_CONSTRUCTOR_PATH",
    default_rel="data/recipe_constructor.json",
    statuses=STATUSES,
    transitions=TRANSITIONS,
    initial_status=STATUS_DRAFT,
)


def store() -> EntityStore:
    return _store


def _str(data: dict[str, Any], key: str) -> str:
    return str(data.get(key) or "").strip()


def _has_markup(value: str) -> bool:
    return "<script" in value.lower() or bool(_HTML_RE.search(value))


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _item_status(item_id: str) -> str:
    if not item_id:
        return ""
    try:
        from services.item_constructor_service import store as item_store
        row = item_store().get(item_id)
        return str((row or {}).get("status") or "")
    except Exception:
        return "published"  # legacy catalog is validated by runtime registry


def _effect_published(effect_id: str) -> bool:
    try:
        from services.effect_constructor_service import store as effect_store
        row = effect_store().get(effect_id)
        return bool(row and row.get("status") == "published")
    except Exception:
        return True


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    """Проверка рецепта перед публикацией (ТЗ §3.4)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not _str(data, "name"):
        errors.append("Не заполнено название рецепта.")
    workshop = _str(data, "workshop")
    if not workshop:
        errors.append("Не выбрана мастерская.")
    elif workshop not in WORKSHOPS:
        errors.append(f"Неизвестная мастерская: {workshop}.")
    workshop_id = _str(data, "workshop_id")
    if workshop_id:
        try:
            from services.workshop_constructor_service import store as workshop_store
            linked = workshop_store().get(workshop_id)
            if not linked or linked.get("status") != STATUS_PUBLISHED:
                errors.append(f"Мастерская «{workshop_id}» не опубликована.")
        except Exception:
            pass

    results = data.get("results") if isinstance(data.get("results"), list) else []
    if not _str(data, "output_item_id") and not any(isinstance(row, dict) and str(row.get("item_id") or "").strip() for row in results):
        errors.append("Не указан ни один результат рецепта.")
    out_amount = _num(data.get("output_amount"))
    if data.get("output_amount") not in (None, "") and (out_amount is None or out_amount < 1):
        errors.append("Количество результата должно быть ≥ 1.")
    out_min = _num(data.get("output_amount_min")) if data.get("output_amount_min") not in (None, "") else None
    out_max = _num(data.get("output_amount_max")) if data.get("output_amount_max") not in (None, "") else None
    if out_min is not None and out_min < 1:
        errors.append("Минимальное количество результата должно быть ≥ 1.")
    if out_min is not None and out_max is not None and out_min > out_max:
        errors.append("Минимальное количество результата больше максимального.")

    ingredients = data.get("ingredients")
    if ingredients in (None, ""):
        warnings.append("У рецепта не указаны ингредиенты.")
    elif not isinstance(ingredients, list):
        errors.append("Ингредиенты должны быть списком.")
    else:
        for index, row in enumerate(ingredients, start=1):
            if not isinstance(row, dict):
                errors.append(f"Ингредиент {index}: неверный формат.")
                continue
            if not str(row.get("item_id") or "").strip():
                if not str(row.get("material_group_id") or "").strip() and not row.get("alternatives"):
                    errors.append(f"Ингредиент {index}: не указан предмет, группа или альтернатива.")
            amount = _num(row.get("amount"))
            if amount is None or amount <= 0:
                errors.append(f"Ингредиент {index}: количество должно быть > 0.")
            role = str(row.get("role") or "").strip()
            if role and role not in MATERIAL_ROLES:
                warnings.append(f"Ингредиент {index}: роль «{role}» не из стандартного списка.")
            if row.get("min_amount") not in (None, "") and row.get("max_amount") not in (None, "") and (_num(row.get("min_amount")) or 0) > (_num(row.get("max_amount")) or 0):
                errors.append(f"Ингредиент {index}: минимум количества больше максимума.")
            iid = str(row.get("item_id") or "").strip()
            if iid and _item_status(iid) not in {"", "published"}:
                errors.append(f"Ингредиент {index}: предмет «{iid}» не опубликован.")
            group_id = str(row.get("material_group_id") or "").strip()
            if group_id:
                try:
                    from services.craft_material_group_service import published as published_group
                    if not published_group(group_id):
                        errors.append(f"Ингредиент {index}: группа материалов «{group_id}» не опубликована.")
                except Exception:
                    pass

    for index, row in enumerate(data.get("tools") or [], start=1):
        if not isinstance(row, dict) or not str(row.get("item_id") or "").strip():
            errors.append(f"Инструмент {index}: не указан предмет.")
            continue
        iid = str(row.get("item_id") or "").strip()
        if _item_status(iid) not in {"", "published"}:
            errors.append(f"Инструмент {index}: предмет «{iid}» не опубликован.")
        if row.get("durability_loss") not in (None, "") and (_num(row.get("durability_loss")) is None or _num(row.get("durability_loss")) < 0):
            errors.append(f"Инструмент {index}: потеря прочности не может быть отрицательной.")

    output_ids = [_str(data, "output_item_id")] + [str(row.get("item_id") or "").strip() for row in results if isinstance(row, dict)] + [str(row.get("item_id") or "").strip() for row in (data.get("byproducts") or []) if isinstance(row, dict)]
    for iid in filter(None, output_ids):
        if _item_status(iid) not in {"", "published"}:
            errors.append(f"Результат «{iid}» не опубликован.")
    for index, row in enumerate(results + list(data.get("byproducts") or []), start=1):
        if not isinstance(row, dict):
            errors.append(f"Результат {index}: неверный формат.")
            continue
        amount = _num(row.get("amount", 1))
        chance = _num(row.get("chance", 100))
        if amount is None or amount <= 0:
            errors.append(f"Результат {index}: количество должно быть больше нуля.")
        if chance is None or chance < 0 or chance > 100:
            errors.append(f"Результат {index}: шанс должен быть 0–100.")

    craft_time = _num(data.get("craft_time"))
    if data.get("craft_time") not in (None, "") and (craft_time is None or craft_time < 0):
        errors.append("Время создания не может быть отрицательным.")
    for key in ("price_copper", "price_silver", "price_gold", "price_magic_gold", "price_ancient"):
        if data.get(key) not in (None, "") and (_num(data.get(key)) is None or _num(data.get(key)) < 0):
            errors.append(f"Поле «{key}» должно быть неотрицательным числом.")
    for key in ("success_chance", "critical_chance", "quality_chance", "fail_chance", "partial_success_chance"):
        value = data.get(key)
        if value in (None, ""):
            continue
        num = _num(value)
        if num is None or num < 0 or num > 100:
            errors.append(f"Поле «{key}» должно быть 0–100.")

    if data.get("blueprint_required") and not _str(data, "blueprint_id"):
        warnings.append("Рецепт требует чертёж, но чертёж (blueprint_id) не указан.")
    if data.get("hidden") and not _str(data, "unlock_condition"):
        warnings.append("Скрытый рецепт без условия открытия — игрок не сможет его получить.")

    # Расширение ремесла (ТЗ 13 §5.6–§5.7).
    recipe_type = _str(data, "recipe_type")
    if recipe_type and recipe_type not in RECIPE_TYPES:
        warnings.append(f"Тип рецепта «{recipe_type}» не из стандартного списка.")
    for key in ("profession_level", "player_level"):
        if data.get(key) in (None, ""):
            continue
        num = _num(data.get(key))
        if num is None or num < 0:
            errors.append(f"Поле «{key}» не может быть отрицательным.")

    for key in ("name", "description"):
        value = _str(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустим HTML.")

    energy = _num(data.get("energy_cost"))
    if data.get("energy_cost") not in (None, "") and (energy is None or energy < 0):
        errors.append("Стоимость энергии не может быть отрицательной.")
    delivery_mode = str(data.get("result_delivery") or "overload")
    if delivery_mode not in RESULT_DELIVERY_MODES:
        errors.append(f"Неизвестный режим выдачи результата: {delivery_mode}.")
    seen_limits: set[str] = set()
    for index, row in enumerate(data.get("weekly_limits") or [], start=1):
        if not isinstance(row, dict):
            errors.append(f"Недельный лимит {index}: неверный формат.")
            continue
        limit_id = str(row.get("id") or "").strip()
        if not limit_id:
            errors.append(f"Недельный лимит {index}: не указан ID.")
        elif limit_id in seen_limits:
            errors.append(f"Недельный лимит {index}: ID «{limit_id}» повторяется.")
        seen_limits.add(limit_id)
        maximum = _num(row.get("max_per_week"))
        if maximum is None or maximum < 0:
            errors.append(f"Недельный лимит {index}: максимум должен быть неотрицательным числом.")
    effect_refs = list(data.get("effect_ids") or []) + list(data.get("result_effects") or []) + [data.get("failure_effect_id"), data.get("failure_curse_id")]
    for effect_id in effect_refs:
        eid = str(effect_id.get("effect_id") if isinstance(effect_id, dict) else effect_id or "").strip()
        if eid and not _effect_published(eid):
            errors.append(f"Эффект «{eid}» не опубликован.")
    for field, kind, label in (("failure_event_id", "event", "Событие провала"), ("failure_battle_mob_id", "mob", "Моб провала")):
        ref = str(data.get(field) or "").strip()
        if ref:
            try:
                from services import world_content_registry as world
                row = world.get_content(kind, ref)
                if not row or row.get("status") != world.STATUS_PUBLISHED:
                    errors.append(f"{label} «{ref}» не опубликован.")
            except Exception:
                pass
    from services.formula_runtime import validate_references
    errors.extend(validate_references(data, FORMULA_FIELDS))
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def where_used(item_id: str) -> list[dict[str, Any]]:
    """Где используется предмет в рецептах (ТЗ §3.3): как результат или ингредиент."""
    oid = str(item_id or "").strip()
    if not oid:
        return []
    refs: list[dict[str, Any]] = []
    for env in _store.list():
        data = env.get("data") or {}
        fields: list[str] = []
        if str(data.get("output_item_id") or "") == oid:
            fields.append("результат рецепта")
        for row in (data.get("ingredients") or []):
            if isinstance(row, dict) and (str(row.get("item_id") or "") == oid or oid in {str(x.get("item_id") if isinstance(x, dict) else x or "") for x in row.get("alternatives") or []}):
                fields.append("ингредиент/альтернатива")
        for row in (data.get("tools") or []):
            if isinstance(row, dict) and str(row.get("item_id") or "") == oid:
                fields.append("инструмент")
        for row in list(data.get("results") or []) + list(data.get("byproducts") or []):
            if isinstance(row, dict) and str(row.get("item_id") or "") == oid:
                fields.append("дополнительный/побочный результат")
        if fields:
            refs.append({"id": env.get("id"), "name": data.get("name") or env.get("id"), "fields": fields})
    return refs


def recipe_usage(recipe_id: str) -> list[dict[str, Any]]:
    """Human-readable dependency graph for the recipe card (§28.2)."""
    env = store().get(recipe_id)
    if not env:
        return []
    data = env.get("data") or {}
    rows: list[dict[str, Any]] = []
    def add(kind: str, oid: Any, field: str) -> None:
        value = str(oid or "").strip()
        if value:
            rows.append({"id": value, "name": value, "kind": kind, "fields": [field]})
    add("workshop", data.get("workshop_id") or data.get("workshop"), "мастерская")
    for key, kind in (("location_ids", "location"), ("sublocation_ids", "sublocation"), ("camp_ids", "camp"), ("npc_ids", "npc"), ("button_ids", "button"), ("event_ids", "event"), ("quest_ids", "quest"), ("weekly_limit_ids", "weekly_limit")):
        for oid in data.get(key) or []:
            add(kind, oid, key)
    for key in FORMULA_FIELDS:
        add("formula", data.get(key), key)
    for oid in data.get("effect_ids") or []:
        add("effect", oid, "влияет на ремесло")
    for ingredient in data.get("ingredients") or []:
        if isinstance(ingredient, dict):
            add("item", ingredient.get("item_id"), "ингредиент")
            add("material_group", ingredient.get("material_group_id"), "группа материалов")
    for tool in data.get("tools") or []:
        if isinstance(tool, dict):
            add("item", tool.get("item_id"), "инструмент")
    add("item", data.get("output_item_id"), "основной результат")
    for result in list(data.get("results") or []) + list(data.get("byproducts") or []):
        if isinstance(result, dict):
            add("item", result.get("item_id"), "результат")
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["kind"], row["id"])
        if key in merged:
            merged[key]["fields"].extend(row["fields"])
        else:
            merged[key] = row
    return list(merged.values())


def _recipe_view(env: dict[str, Any], *, role: str, amount: Any = None, consumed: bool | None = None) -> dict[str, Any]:
    data = env.get("data") or {}
    workshop = str(data.get("workshop") or "")
    return {
        "id": env.get("id"), "name": data.get("name") or env.get("id"),
        "workshop": workshop, "workshop_label": WORKSHOP_LABELS.get(workshop, workshop),
        "status": env.get("status"), "role": role,
        "output_item_id": data.get("output_item_id"),
        "output_amount": data.get("output_amount"),
        "amount": amount, "consumed": consumed,
    }


def item_craft_usage(item_id: str) -> dict[str, Any]:
    """Полное использование предмета в ремесле (ТЗ 13 §6): по ролям + цепочка + ошибки."""
    oid = str(item_id or "").strip()
    as_result: list[dict[str, Any]] = []
    as_material: list[dict[str, Any]] = []
    as_blueprint: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []
    if not oid:
        return {"as_result": [], "as_material": [], "as_blueprint": [], "errors": [], "warnings": [], "chain": {}}

    for env in _store.list():
        data = env.get("data") or {}
        status = env.get("status")
        if str(data.get("output_item_id") or "") == oid:
            as_result.append(_recipe_view(env, role="result"))
            if status == STATUS_DISABLED:
                warnings.append(f"Предмет — результат рецепта «{data.get('name') or env.get('id')}», но рецепт отключён.")
        for row in (data.get("ingredients") or []):
            if isinstance(row, dict) and str(row.get("item_id") or "") == oid:
                as_material.append(_recipe_view(env, role="material", amount=row.get("amount"), consumed=True))
                if status == STATUS_DISABLED:
                    warnings.append(f"Предмет — материал рецепта «{data.get('name') or env.get('id')}», но рецепт отключён.")
                break
        if str(data.get("blueprint_id") or "") == oid:
            as_blueprint.append(_recipe_view(env, role="blueprint"))

    # §6.7: материал нигде не создаётся (нет рецепта-результата), но используется.
    if as_material and not as_result:
        warnings.append("Предмет используется как материал, но ни один рецепт его не создаёт.")

    # Мини-цепочка (§6.5): из чего делается этот предмет и что из него делают.
    made_from: list[str] = []
    for r in as_result:
        env = _store.get(r["id"]) or {}
        for row in ((env.get("data") or {}).get("ingredients") or []):
            if isinstance(row, dict) and str(row.get("item_id") or "").strip():
                made_from.append(str(row["item_id"]).strip())
    makes = [r.get("output_item_id") for r in as_material if r.get("output_item_id")]
    chain = {"made_from": sorted(set(made_from)), "makes": sorted(set(filter(None, makes)))}

    return {"as_result": as_result, "as_material": as_material, "as_blueprint": as_blueprint,
            "errors": errors, "warnings": warnings, "chain": chain}


def published_runtime_recipes() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for env in store().list(status=STATUS_PUBLISHED):
        data = dict(env.get("data") or {})
        data["id"] = str(env.get("id") or "")
        data["constructor_live"] = True
        data["constructor_version"] = env.get("version")
        normalized_output = {"item_id": data.get("output_item_id"), "amount": data.get("output_amount", 1),
                             "amount_min": data.get("output_amount_min"), "amount_max": data.get("output_amount_max")}
        data.setdefault("result", normalized_output)
        data.setdefault("output", normalized_output)
        data.setdefault("requirements", data.get("ingredients") or [])
        data.setdefault("craft_time_seconds", data.get("craft_time", 0))
        out.append(data)
    return out
