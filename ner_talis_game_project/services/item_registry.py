"""Item registry and asset enrichment helpers for Ner-Talis.

The registry is intentionally data-driven. It reads imported item metadata from
``data/items_*.json`` and can be reused by Telegram, VK, the future
site API, and tests without hard-coding icons or item ids in event logic.
"""

from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from project_paths import project_path, resolve_project_path

ITEMS_HILLY_MEADOWS_PATH = project_path("data", "items_hilly_meadows.json")
ITEMS_REGISTRY_GLOB = "items_*.json"

CATEGORY_TO_RU = {
    "camp_food": "Еда",
    "ingredients": "Ингредиенты",
    "resources": "Ресурсы",
    "currency": "Валюта",
    "items": "Предметы",
    "trophies": "Трофеи",
    "equipment": "Экипировка",
}

TYPE_TO_RU = {
    "food": "Еда",
    "drink": "Напиток",
    "liquid": "Жидкость",
    "powder": "Порошок",
    "mushroom": "Гриб",
    "root": "Корень",
    "meat": "Мясо",
    "herb": "Трава",
    "berry": "Ягоды",
    "stone": "Камень",
    "ore": "Руда",
    "scrap": "Лом",
    "coin": "Монета",
    "knife": "Нож",
    "hide": "Шкура",
    "pelt": "Шкурка",
    "fang": "Клык",
    "tooth": "Зуб",
    "claw": "Коготь",
    "horn": "Рог",
    "tendon": "Сухожилие",
    "wood": "Дерево",
    "fabric": "Ткань",
    "gloves": "Перчатки",
    "belt": "Пояс",
    "fat": "Жир",
    "event": "Событие",
}

QUALITY_TO_RU = {
    "common": "обычный",
    "uncommon": "необычный",
    "rare": "редкий",
    "epic": "эпический",
    "legendary": "легендарный",
    "mythic": "мифический",
    "divine": "божественный",
}


def _public_icon_path(icon: str | None) -> str | None:
    if not icon:
        return None
    icon = str(icon).replace("\\\\", "/").replace("\\", "/").strip()
    if icon.startswith("/") or icon.startswith("http://") or icon.startswith("https://"):
        return icon
    return "/" + icon.lstrip("/")


@lru_cache(maxsize=8)
def load_item_definitions(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load one item registry file.

    Keeping the no-argument call tied to the original hilly-meadows file
    preserves backward compatibility for tests and import tools. Runtime
    lookups use ``load_all_item_definitions`` so location packs are still
    available everywhere.
    """

    items_path = resolve_project_path(path) if path else ITEMS_HILLY_MEADOWS_PATH
    if not items_path.exists():
        return []
    with items_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, list):
        raise ValueError(f"Item registry must be a list: {items_path}")
    return [item for item in payload if isinstance(item, dict)]


@lru_cache(maxsize=8)
def load_all_item_definitions() -> list[dict[str, Any]]:
    """Load every gameplay item registry from ``data/items_*.json``."""

    data_dir = project_path("data")
    paths = [
        candidate
        for candidate in sorted(data_dir.glob(ITEMS_REGISTRY_GLOB))
        if not candidate.name.startswith("items_import_")
    ]
    if not paths and ITEMS_HILLY_MEADOWS_PATH.exists():
        paths = [ITEMS_HILLY_MEADOWS_PATH]

    definitions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for items_path in paths:
        for item in load_item_definitions(items_path):
            item_id = str(item.get("id") or item.get("item_id") or "").strip()
            if item_id and item_id in seen_ids:
                continue
            if item_id:
                seen_ids.add(item_id)
            definitions.append(item)
    return definitions


@lru_cache(maxsize=8)
def _indexes(path: str | Path | None = None) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    for item in (load_item_definitions(path) if path else load_all_item_definitions()):
        item_id = str(item.get("id") or "").strip()
        item_name = str(item.get("name_ru") or item.get("name") or "").strip()
        if item_id:
            by_id[item_id] = item
        if item_name:
            by_name[item_name.casefold()] = item
    return by_id, by_name


def get_item_definition(item_id_or_name: str, path: str | Path | None = None) -> dict[str, Any] | None:
    if not item_id_or_name:
        return None
    by_id, by_name = _indexes(path)
    key = str(item_id_or_name).strip()
    return by_id.get(key) or by_name.get(key.casefold())


def get_item_definition_by_name(name: str, path: str | Path | None = None) -> dict[str, Any] | None:
    if not name:
        return None
    return _indexes(path)[1].get(str(name).strip().casefold())


def get_item_definition_by_id(item_id: str, path: str | Path | None = None) -> dict[str, Any] | None:
    if not item_id:
        return None
    return _indexes(path)[0].get(str(item_id).strip())


def registry_item_to_inventory_item(definition: dict[str, Any], amount: int = 1) -> dict[str, Any]:
    """Converts imported asset metadata into the inventory item shape used by the project."""
    item = deepcopy(definition)
    item_id = str(item.get("id") or item.get("item_id") or item.get("name_ru") or "item")
    name = str(item.get("name_ru") or item.get("name") or item_id)
    category = CATEGORY_TO_RU.get(str(item.get("category") or "").casefold(), item.get("category") or "Прочее")
    subtype = TYPE_TO_RU.get(str(item.get("subtype") or "").casefold(), item.get("subtype") or "Предмет")
    quality = QUALITY_TO_RU.get(str(item.get("quality") or "").casefold(), item.get("quality") or "обычный")
    max_stack = int(item.get("stack_size") or item.get("max_stack") or (20 if item.get("stackable") else 1))
    max_stack = max(1, max_stack)
    result = {
        **item,
        "id": item_id,
        "item_id": item_id,
        "name": name,
        "name_ru": name,
        "category": category,
        "type": subtype,
        "subtype": subtype,
        "quality": quality,
        "amount": max(1, int(amount or 1)),
        "max_stack": max_stack,
        "stackable": bool(item.get("stackable", max_stack > 1)),
        "icon": _public_icon_path(item.get("icon")),
        "asset_icon": _public_icon_path(item.get("icon")),
        "description": item.get("description") or "Описание предмета пока не добавлено.",
    }
    # Currency is stored in money fields, not as inventory items, but the visual
    # definitions stay in the registry for UI rendering and future logs.
    if result.get("energy_restore"):
        result.setdefault("use_effect", {"energy_restore": result["energy_restore"]})
    return result


def build_inventory_item(name: str, amount: int = 1, *, item_id: str | None = None, max_stack: int | None = None) -> dict[str, Any]:
    definition = get_item_definition_by_id(item_id or "") if item_id else None
    definition = definition or get_item_definition_by_name(name)
    if definition:
        item = registry_item_to_inventory_item(definition, amount)
        if max_stack is not None:
            item["max_stack"] = max(1, int(max_stack))
        return item
    return {
        "id": item_id or slugify_fallback_item_id(name),
        "item_id": item_id or slugify_fallback_item_id(name),
        "name": name,
        "category": "Ресурсы",
        "type": "Материал",
        "quality": "обычный",
        "amount": max(1, int(amount or 1)),
        "max_stack": max(1, int(max_stack or 999)),
        "source": "Нер-Талис",
        "actions": [],
    }


def enrich_inventory_item(item: dict[str, Any]) -> dict[str, Any]:
    """Adds id/icon/category metadata to old inventory entries when possible."""
    if not isinstance(item, dict):
        return item
    definition = get_item_definition_by_id(str(item.get("id") or item.get("item_id") or ""))
    definition = definition or get_item_definition_by_name(str(item.get("name") or item.get("name_ru") or ""))
    if not definition:
        return item
    enriched = registry_item_to_inventory_item(definition, int(item.get("amount", 1) or 1))
    # Preserve gameplay-specific fields already written into the profile.
    for key, value in item.items():
        if value is not None and key not in {"icon", "asset_icon", "category", "type", "subtype", "quality", "max_stack", "stack_size"}:
            enriched[key] = value
    return enriched


def slugify_fallback_item_id(name: str) -> str:
    replacements = {" ": "_", "ё": "е", "Ё": "Е", "×": "x"}
    result = str(name or "item").casefold()
    for old, new in replacements.items():
        result = result.replace(old, new)
    return "item_" + "".join(ch for ch in result if ch.isalnum() or ch == "_")


# Backward-compatible names for future loaders.
HILLY_MEADOWS_ITEM_ASSETS = load_item_definitions(ITEMS_HILLY_MEADOWS_PATH)
ALL_ITEM_ASSETS = load_all_item_definitions()
