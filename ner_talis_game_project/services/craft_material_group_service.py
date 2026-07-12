"""Published material groups for crafting ingredients (ТЗ ремесла §9.4)."""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403

_HTML_RE = re.compile(r"<[^>]+>")
_store = EntityStore(
    env_var="CRAFT_MATERIAL_GROUP_PATH",
    default_rel="data/craft_material_groups.json",
    statuses=STATUSES, transitions=TRANSITIONS, initial_status=STATUS_DRAFT,  # noqa: F405
)


def store() -> EntityStore:
    return _store


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []
    if not str(data.get("name") or "").strip():
        errors.append("Не заполнено название группы материалов.")
    if not any(data.get(key) for key in ("item_ids", "categories", "allowed_qualities", "item_types")):
        errors.append("Группа материалов должна содержать предметы или правила отбора.")
    minimum = data.get("min_item_level")
    maximum = data.get("max_item_level")
    try:
        if minimum not in (None, "") and maximum not in (None, "") and float(minimum) > float(maximum):
            errors.append("Минимальный уровень предмета больше максимального.")
    except (TypeError, ValueError):
        errors.append("Уровни предмета должны быть числами.")
    for key in ("name", "description"):
        value = str(data.get(key) or "")
        if value and (_HTML_RE.search(value) or "<script" in value.lower()):
            errors.append(f"В поле «{key}» недопустим HTML.")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def published(group_id: str) -> dict[str, Any] | None:
    row = store().get(group_id)
    return dict(row.get("data") or {}) if row and row.get("status") == STATUS_PUBLISHED else None  # noqa: F405


def matches(item: dict[str, Any], group_id: str) -> bool:
    group = published(group_id)
    if not group:
        return False
    item_id = str(item.get("item_id") or item.get("id") or "")
    category = str(item.get("category") or "")
    item_type = str(item.get("item_type") or item.get("type") or item.get("subtype") or "")
    quality = str(item.get("quality") or "common")
    level = int(float(item.get("item_level", item.get("level", 0)) or 0))
    if group.get("item_ids") and item_id not in {str(x) for x in group.get("item_ids") or []}:
        return False
    if group.get("categories") and category not in {str(x) for x in group.get("categories") or []}:
        return False
    if group.get("item_types") and item_type not in {str(x) for x in group.get("item_types") or []}:
        return False
    if group.get("allowed_qualities") and quality not in {str(x) for x in group.get("allowed_qualities") or []}:
        return False
    if quality in {str(x) for x in group.get("forbidden_qualities") or []}:
        return False
    if group.get("min_item_level") not in (None, "") and level < int(float(group["min_item_level"])):
        return False
    if group.get("max_item_level") not in (None, "") and level > int(float(group["max_item_level"])):
        return False
    return True


def where_used(group_id: str) -> list[dict[str, Any]]:
    from services import recipe_constructor_service as recipes
    out = []
    for env in recipes.store().list():
        data = env.get("data") or {}
        if any(isinstance(row, dict) and str(row.get("material_group_id") or "") == str(group_id) for row in data.get("ingredients") or []):
            out.append({"id": env.get("id"), "name": data.get("name") or env.get("id"), "kind": "recipe", "fields": ["ингредиент: группа материалов"]})
    return out
