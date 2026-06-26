"""Конструктор ремесла V2 (ТЗ «импорт ремесла») — авторская часть.

Здесь админ задаёт РЕЦЕПТЫ ремесла: мастерская/раздел, результат, ингредиенты,
время, шансы успеха/качества/провала, чертёж, скрытость. Это слой данных +
валидация; рантайм крафта — services/crafting_service.py (мастерские, выполнение
рецептов из data/crafting_recipes.json). Хранение — генерик EntityStore
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

    if not _str(data, "output_item_id"):
        errors.append("Не указан результат рецепта (output_item_id).")
    out_amount = _num(data.get("output_amount"))
    if data.get("output_amount") not in (None, "") and (out_amount is None or out_amount < 1):
        errors.append("Количество результата должно быть ≥ 1.")

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
                errors.append(f"Ингредиент {index}: не указан предмет.")
            amount = _num(row.get("amount"))
            if amount is None or amount <= 0:
                errors.append(f"Ингредиент {index}: количество должно быть > 0.")

    craft_time = _num(data.get("craft_time"))
    if data.get("craft_time") not in (None, "") and (craft_time is None or craft_time < 0):
        errors.append("Время создания не может быть отрицательным.")
    for key in ("success_chance", "quality_chance", "fail_chance"):
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

    for key in ("name", "description"):
        value = _str(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустим HTML.")

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
            if isinstance(row, dict) and str(row.get("item_id") or "") == oid:
                fields.append("ингредиент")
                break
        if fields:
            refs.append({"id": env.get("id"), "name": data.get("name") or env.get("id"), "fields": fields})
    return refs


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
