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


def _item_registry_paths() -> list[Path]:
    data_dir = project_path("data")
    paths = [
        candidate
        for candidate in sorted(data_dir.glob(ITEMS_REGISTRY_GLOB))
        if not candidate.name.startswith("items_import_")
    ]
    if not paths and ITEMS_HILLY_MEADOWS_PATH.exists():
        paths = [ITEMS_HILLY_MEADOWS_PATH]
    return paths


def _registry_item_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("item_id") or "").strip()


def _canonical_duplicate_payload(item: dict[str, Any]) -> str:
    normalized = deepcopy(item)
    item_id = _registry_item_id(normalized)
    normalized["id"] = item_id
    normalized.pop("item_id", None)
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True)


def validate_item_registry_duplicates(paths: list[Path] | None = None) -> None:
    """Fail when item registry files define the same id differently."""

    seen: dict[str, tuple[str, Path]] = {}
    conflicts: list[str] = []
    for items_path in paths or _item_registry_paths():
        for item in load_item_definitions(items_path):
            item_id = _registry_item_id(item)
            if not item_id:
                continue
            payload = _canonical_duplicate_payload(item)
            previous = seen.get(item_id)
            if previous is None:
                seen[item_id] = (payload, items_path)
                continue
            previous_payload, previous_path = previous
            if payload != previous_payload:
                conflicts.append(f"{item_id}: {previous_path} vs {items_path}")
    if conflicts:
        details = "; ".join(conflicts)
        raise ValueError(f"Conflicting duplicate item ids in registry: {details}")



LEGACY_STARTING_LOOT_ID_ALIASES = {
    "dense_hide": "simple_hide",
    "jackal_hide": "simple_hide",
    "small_hide": "simple_hide",
    "small_pelt": "simple_hide",
    "deer_hide": "simple_hide",
    "wolf_hide": "simple_hide",
    "boar_hide": "simple_hide",
    "bear_hide": "simple_hide",
    "strong_tendon": "simple_tendon",
    "tough_tendon": "simple_tendon",
    "strong_sinew": "simple_tendon",
    "tough_sinew": "simple_tendon",
}
LEGACY_STARTING_LOOT_NAME_ALIASES = {
    "плотная шкура": "simple_hide",
    "шкура шакала": "simple_hide",
    "маленькая шкура": "simple_hide",
    "маленькая шкурка": "simple_hide",
    "оленья шкура": "simple_hide",
    "волчья шкура": "simple_hide",
    "кабанья шкура": "simple_hide",
    "медвежья шкура": "simple_hide",
    "крепкое сухожилие": "simple_tendon",
    "жёсткое сухожилие": "simple_tendon",
    "жесткое сухожилие": "simple_tendon",
}


def canonical_starting_loot_id(value: str | None) -> str:
    key = str(value or "").strip()
    return LEGACY_STARTING_LOOT_ID_ALIASES.get(key, key)


def canonical_starting_loot_name_id(value: str | None) -> str | None:
    key = str(value or "").strip().casefold()
    return LEGACY_STARTING_LOOT_NAME_ALIASES.get(key)

CATEGORY_TO_RU = {
    "camp_food": "Еда",
    "consumable": "Расходники",
    "consumables": "Расходники",
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
    "flower": "Цветы",
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
    "quiver": "Колчан",
    "arrow_quiver": "Колчан стрел",
    "bolt_quiver": "Колчан болтов",
    "ammunition": "Боеприпас",
    "arrow": "Стрела",
    "bolt": "Болт",
    "glass_gem": "драг. камень",
    "gem_imitation": "драг. камень",
    "material": "Материал",
    "ingot": "Слиток",
    "plate": "Пластина",
    "leather": "Кожа",
    "paper": "Бумага",
    "recipe": "Рецепт",
    "blueprint": "Чертёж",
    "weapon": "Оружие",
    "sword": "Меч",
    "ring": "Кольцо",
    "necklace": "Ожерелье",
    "junk": "Хлам",
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


ITEM_SPECIFIC_TYPE_RU = {
    "fabric_pieces": "Хлам",
    "old_knife": "Хлам",
    "iron_scrap": "Хлам",
}

ITEM_SPECIFIC_STACK_LIMITS = {
    "clean_water": 20,
    "muddy_water": 20,
    "old_knife": 20,
    "iron_scrap": 20,
}

STACK_40_SUBTYPES = {"berry", "herb", "flower", "root", "mushroom", "ягоды", "ягода", "трава", "травы", "цветы", "цветок", "корень", "корни", "гриб", "грибы"}
STACK_10_SUBTYPES = {"stone", "ore", "wood", "камень", "камни", "руда", "руды", "дерево", "древесина"}
STACK_30_SUBTYPES = {"fang", "tooth", "tendon", "claw", "клык", "клыки", "зуб", "зубы", "сухожилие", "сухожилия", "коготь", "когти"}
NON_STACKABLE_CATEGORIES = {"снаряжение", "оружие", "бижутерия", "equipment", "weapon", "weapons", "jewelry", "jewellery"}


def inventory_stack_limit_from_definition(item: dict[str, Any]) -> int:
    """Return the gameplay stack size limit for a registry item."""

    item_id = str(item.get("id") or item.get("item_id") or "").strip()
    if item_id in ITEM_SPECIFIC_STACK_LIMITS:
        return ITEM_SPECIFIC_STACK_LIMITS[item_id]

    category = str(item.get("category") or "").casefold()
    item_class = str(item.get("item_class") or "").casefold()
    type_value = str(item.get("type") or "").casefold()
    subtype = str(item.get("subtype") or "").casefold()
    slot = str(item.get("slot") or item.get("equipment_slot") or item.get("targetSlotKey") or item.get("slotKey") or "").strip()

    if slot or category in NON_STACKABLE_CATEGORIES or item_class in NON_STACKABLE_CATEGORIES or type_value in NON_STACKABLE_CATEGORIES:
        return 1
    if subtype in STACK_40_SUBTYPES or type_value in STACK_40_SUBTYPES:
        return 40
    if subtype in STACK_10_SUBTYPES or type_value in STACK_10_SUBTYPES:
        return 10
    if subtype in STACK_30_SUBTYPES or type_value in STACK_30_SUBTYPES:
        return 30

    raw = item.get("max_stack", item.get("stack_size"))
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 20 if item.get("stackable") else 1


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


ICON_OVERRIDE_KEYS = ("icon", "asset_icon", "asset_path", "asset_filename", "image")


def _icon_overrides_path() -> Path:
    import os

    raw = os.getenv("ICON_OVERRIDES_PATH")
    if raw:
        return resolve_project_path(raw)
    # By default the overrides file lives next to the uploaded item images, in
    # the same persistent uploads volume.
    base = os.getenv("PUBLIC_UPLOADS_ASSETS_DIR", "data/public_uploads/assets")
    return resolve_project_path(base) / "admin_uploads" / "icon_overrides.json"


@lru_cache(maxsize=1)
def load_icon_overrides() -> dict[str, str]:
    """Admin icon overrides persisted in the runtime volume.

    The admin panel can change an item's image. Writing that into ``data/*.json``
    does not survive a container rebuild (those files are baked into the image),
    so the durable source of truth is this JSON file inside the uploads volume.
    """

    path = _icon_overrides_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    result: dict[str, str] = {}
    for item_id, icon in payload.items():
        if isinstance(item_id, str) and isinstance(icon, str) and item_id.strip() and icon.strip():
            result[item_id.strip()] = icon.strip()
    return result


def set_icon_override(item_id: str, icon_path: str, overrides_path: str | Path | None = None) -> None:
    """Persist one item icon override and refresh registry caches.

    ``overrides_path`` lets the caller pin the file to a specific uploads volume
    (the admin image handler passes the dir it actually wrote the image into, so
    tests that redirect the uploads dir stay isolated).
    """

    cleaned_id = str(item_id or "").strip()
    cleaned_icon = str(icon_path or "").strip()
    if not cleaned_id or not cleaned_icon:
        return
    path = Path(overrides_path) if overrides_path else _icon_overrides_path()
    existing: dict[str, str] = {}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                existing = {str(k): str(v) for k, v in payload.items() if isinstance(k, str) and isinstance(v, str)}
        except Exception:
            existing = {}
    existing[cleaned_id] = cleaned_icon
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    invalidate_registry_caches()


def invalidate_registry_caches() -> None:
    load_icon_overrides.cache_clear()
    load_all_item_definitions.cache_clear()
    _indexes.cache_clear()
    # Downstream caches that derive from the registry (e.g. the admin catalog).
    try:
        from services.admin_panel_service import invalidate_admin_catalog_cache
        invalidate_admin_catalog_cache()
    except Exception:
        pass


def _apply_icon_override(item: dict[str, Any], overrides: dict[str, str]) -> dict[str, Any]:
    item_id = str(item.get("id") or item.get("item_id") or "").strip()
    icon = overrides.get(item_id)
    if not icon:
        return item
    patched = dict(item)
    for key in ICON_OVERRIDE_KEYS:
        if key in patched or key in {"icon", "asset_icon"}:
            patched[key] = icon
    return patched


@lru_cache(maxsize=8)
def load_all_item_definitions() -> list[dict[str, Any]]:
    """Load every gameplay item registry from ``data/items_*.json``."""

    paths = _item_registry_paths()
    validate_item_registry_duplicates(paths)
    overrides = load_icon_overrides()

    definitions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for items_path in paths:
        for item in load_item_definitions(items_path):
            item_id = str(item.get("id") or item.get("item_id") or "").strip()
            if item_id and item_id in seen_ids:
                continue
            if item_id:
                seen_ids.add(item_id)
            definitions.append(_apply_icon_override(item, overrides) if overrides else item)

    # Starter gear lives in Python game-data, not in data/items_*.json.
    # Include it in runtime lookups so old saved starter items can be enriched
    # with sale prices/icons and can appear in NPC sell lists.
    try:
        from game_data.starter_items import STARTER_ITEMS
    except Exception:
        STARTER_ITEMS = []
    for item in STARTER_ITEMS:
        item_id = str(item.get("id") or item.get("item_id") or "").strip()
        if item_id and item_id in seen_ids:
            continue
        if item_id:
            seen_ids.add(item_id)
        definitions.append(_apply_icon_override(item, overrides) if overrides else item)
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
            by_name.setdefault(item_name.casefold(), item)
    return by_id, by_name


def get_item_definition(item_id_or_name: str, path: str | Path | None = None) -> dict[str, Any] | None:
    if not item_id_or_name:
        return None
    by_id, by_name = _indexes(path)
    key = str(item_id_or_name).strip()
    canonical_id = canonical_starting_loot_id(key)
    if canonical_id in by_id:
        return by_id.get(canonical_id)
    name_alias_id = canonical_starting_loot_name_id(key)
    if name_alias_id:
        return by_id.get(name_alias_id)
    return by_id.get(key) or by_name.get(key.casefold())


def get_item_definition_by_name(name: str, path: str | Path | None = None) -> dict[str, Any] | None:
    if not name:
        return None
    indexes = _indexes(path)
    canonical_id = canonical_starting_loot_name_id(name)
    if canonical_id:
        return indexes[0].get(canonical_id)
    return indexes[1].get(str(name).strip().casefold())


def get_item_definition_by_id(item_id: str, path: str | Path | None = None) -> dict[str, Any] | None:
    if not item_id:
        return None
    return _indexes(path)[0].get(canonical_starting_loot_id(str(item_id).strip()))


def registry_item_to_inventory_item(definition: dict[str, Any], amount: int = 1) -> dict[str, Any]:
    """Converts imported asset metadata into the inventory item shape used by the project."""
    item = deepcopy(definition)
    item_id = str(item.get("id") or item.get("item_id") or item.get("name_ru") or "item")
    name = str(item.get("name_ru") or item.get("name") or item_id)
    category = CATEGORY_TO_RU.get(str(item.get("category") or "").casefold(), item.get("category") or "Прочее")
    subtype = TYPE_TO_RU.get(str(item.get("subtype") or "").casefold(), item.get("subtype") or "Предмет")
    quality = QUALITY_TO_RU.get(str(item.get("quality") or "").casefold(), item.get("quality") or "обычный")
    max_stack = inventory_stack_limit_from_definition(item)
    result = {
        **item,
        "id": item_id,
        "item_id": item_id,
        "name": name,
        "name_ru": name,
        "category": category,
        "type": ITEM_SPECIFIC_TYPE_RU.get(item_id, subtype),
        "subtype": ITEM_SPECIFIC_TYPE_RU.get(item_id, subtype),
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
    canonical_item_id = canonical_starting_loot_id(item_id or "") if item_id else canonical_starting_loot_name_id(name)
    definition = get_item_definition_by_id(canonical_item_id or "") if canonical_item_id else None
    definition = definition or get_item_definition_by_name(name)
    if definition:
        item = registry_item_to_inventory_item(definition, amount)
        if max_stack is not None:
            item["max_stack"] = max(1, int(max_stack))
        return item
    return {
        "id": canonical_item_id or item_id or slugify_fallback_item_id(name),
        "item_id": canonical_item_id or item_id or slugify_fallback_item_id(name),
        "name": name,
        "category": "Ресурсы",
        "type": "Материал",
        "quality": "обычный",
        "amount": max(1, int(amount or 1)),
        "max_stack": max(1, int(max_stack or 20)),
        "source": "Нер-Талис",
        "actions": [],
    }


def enrich_inventory_item(item: dict[str, Any]) -> dict[str, Any]:
    """Adds id/icon/category metadata to old inventory entries when possible."""
    if not isinstance(item, dict):
        return item
    item = dict(item)
    legacy_id = str(item.get("id") or item.get("item_id") or "").strip()
    canonical_id = canonical_starting_loot_id(legacy_id) if legacy_id else canonical_starting_loot_name_id(str(item.get("name") or item.get("name_ru") or ""))
    if canonical_id and canonical_id != legacy_id:
        item["id"] = canonical_id
        item["item_id"] = canonical_id
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
