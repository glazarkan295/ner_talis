"""Админ-панель сайта Нер-Талис.

Сервис не использует eval/сырой SQL для пользовательских данных. Все опасные
операции требуют активной админ-сессии, созданной из разрешённого админ-чата.
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import mimetypes
import os
import re
import secrets
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from project_paths import resolve_project_path
from services.admin_audit import write_admin_audit
from services.admin_player_service import (
    backup_player,
    delete_player_profile,
    find_players,
    format_player_admin_summary,
    normalize_game_id,
)
from services.inventory_service import add_inventory_item, recalculate_inventory_overflow
from services.item_registry import (
    build_inventory_item,
    get_item_definition_by_id,
    load_all_item_definitions,
    registry_item_to_inventory_item,
)
from services.progression_service import grant_exact_experience
from services.promo_service import add_promo_code, delete_promo_code, list_promo_codes, load_promo_data

ADMIN_PANEL_SCOPE = "admin_panel"
ADMIN_PLAYER_VIEW_SCOPE = "admin_player_view"
ADMIN_PLAYER_VIEW_TTL_MINUTES = 30
DEFAULT_ADMIN_PANEL_TTL_MINUTES = 60
MAX_REWARD_AMOUNT = 1_000_000_000
# Денежные награды задаются в монетах разного номинала, но зачисляются в медь.
# Ограничиваем итоговую медь, иначе высокий номинал (×500 млрд за древнюю) даёт
# переполнение 64-битных денежных колонок SQLite/Postgres при доставке/промо.
MAX_REWARD_MONEY_COPPER = 1_000_000_000_000_000  # 1e15 меди — с большим запасом до 2^63-1
PUBLIC_UPLOADS_ASSETS_DIR = os.getenv("PUBLIC_UPLOADS_ASSETS_DIR", "data/public_uploads/assets")
SYNTHETIC_REWARD_IDS = {
    "money_copper": {
        "id": "money_copper",
        "item_id": "money_copper",
        "kind": "money",
        "copper_per_unit": 1,
        "name": "Медные монеты",
        "category": "Админ-ресурсы",
        "description": "Валюта (медь). При доставке или промокоде зачисляется на баланс игрока, а не в инвентарь.",
        "icon": "/assets/items/hilly_meadows/currency/copper_coin.png",
    },
    "money_silver": {
        "id": "money_silver",
        "item_id": "money_silver",
        "kind": "money",
        "copper_per_unit": 1_000,
        "name": "Серебряные монеты",
        "category": "Админ-ресурсы",
        "description": "Валюта (серебро). 1 серебряная = 1 000 медных. Зачисляется на баланс игрока.",
        "icon": "/assets/items/hilly_meadows/currency/silver_coin.png",
    },
    "money_gold": {
        "id": "money_gold",
        "item_id": "money_gold",
        "kind": "money",
        "copper_per_unit": 1_000_000,
        "name": "Золотые монеты",
        "category": "Админ-ресурсы",
        "description": "Валюта (золото). 1 золотая = 1 000 000 медных. Зачисляется на баланс игрока.",
        "icon": "/assets/items/currency/gold_coin.png",
    },
    "money_magic_gold": {
        "id": "money_magic_gold",
        "item_id": "money_magic_gold",
        "kind": "money",
        "copper_per_unit": 1_000_000_000,
        "name": "Магическое золото",
        "category": "Админ-ресурсы",
        "description": "Валюта (магическое золото). 1 = 1 000 000 000 медных. Зачисляется на баланс игрока.",
        "icon": "/assets/items/currency/magic_gold_coin.png",
    },
    "money_ancient": {
        "id": "money_ancient",
        "item_id": "money_ancient",
        "kind": "money",
        "copper_per_unit": 500_000_000_000,
        "name": "Древние монеты",
        "category": "Админ-ресурсы",
        "description": "Валюта (древние). 1 древняя = 500 000 000 000 медных. Зачисляется на баланс игрока.",
        "icon": "/assets/items/currency/ancient_coin.png",
    },
    "free_skill_points": {
        "id": "free_skill_points",
        "item_id": "free_skill_points",
        "kind": "skill_points",
        "name": "Очки навыков",
        "category": "Админ-ресурсы",
        "description": "1 единица = 1 свободное очко навыков. Зачисляется на баланс игрока.",
        "icon": "/assets/admin_rewards/skill_points.png",
    },
    "free_stat_points": {
        "id": "free_stat_points",
        "item_id": "free_stat_points",
        "kind": "stat_points",
        "name": "Очки характеристик",
        "category": "Админ-ресурсы",
        "description": "1 единица = 1 свободное очко характеристик. Зачисляется на баланс игрока.",
        "icon": "/assets/admin_rewards/stat_points.png",
    },
    "experience_shards": {
        "id": "experience_shards",
        "item_id": "experience_shards",
        "kind": "experience",
        "name": "Крупицы опыта",
        "category": "Админ-ресурсы",
        "description": "1 крупица = 1 единица опыта. Зачисляется напрямую в опыт игрока.",
        "icon": "/assets/admin_rewards/experience_shards.png",
    },
}

# Catalog items that должны быть скрыты из админ-каталога (валюта вынесена в
# Админ-ресурсы, у событий нет моделек, простые рецепты/чертежи выведены из
# контента). Грубая медная бижутерия и простой ювелирный рецепт удалены из
# данных полностью, поэтому здесь их перечислять не нужно.
HIDDEN_CATALOG_ITEM_IDS = {
    "silver_coin",
    "copper_coin",
    "forest_tick",
    "old_bear_trap",
    "mire_trap",
    "simple_leather_recipe",
    "basic_weapon_blueprint",
}

CATEGORY_RU_LABELS = {
    "admin-resources": "Админ-ресурсы",
    "admin_resources": "Админ-ресурсы",
    "weapon": "Оружие",
    "weapons": "Оружие",
    "armor": "Снаряжение",
    "equipment": "Снаряжение",
    "перчатки": "Снаряжение",
    "пояс": "Снаряжение",
    "jewelry": "Бижутерия",
    "accessory": "Бижутерия",
    "ring": "Бижутерия",
    "necklace": "Бижутерия",
    "consumable": "Расходники",
    "consumables": "Расходники",
    "potion": "Расходники",
    "camp_food": "Расходники",
    "resource": "Ресурсы",
    "resources": "Ресурсы",
    "material": "Материалы",
    "materials": "Материалы",
    "crafting_material": "Материалы",
    "ingredient": "Ингредиенты",
    "ingredients": "Ингредиенты",
    "fat": "Ингредиенты",
    "loot": "Добыча",
    "mob_loot": "Добыча",
    "drop": "Добыча",
    "trophy": "Добыча",
    "trophies": "Добыча",
    "meat": "Добыча",
    "мясо": "Добыча",
    "hide": "Добыча",
    "шкура": "Добыча",
    "fang": "Добыча",
    "fangs": "Добыча",
    "клыки": "Добыча",
    "claw": "Добыча",
    "claws": "Добыча",
    "когти": "Добыча",
    "horn": "Добыча",
    "horns": "Добыча",
    "рога": "Добыча",
    "tendon": "Добыча",
    "tendons": "Добыча",
    "сухожилия": "Добыча",
    "junk": "Хлам",
    "trash": "Хлам",
    "misc": "Прочее",
    "other": "Прочее",
    "evidence": "Особое",
    "special": "Особое",
    "tool": "Инструменты",
    "tools": "Инструменты",
    "currency": "Валюта",
    "events": "События",
    "artifact": "Артефакты",
    "ammunition": "Боеприпасы",
    "quiver": "Колчаны",
}


def _category_ru(value: Any, fallback: str = "Прочее") -> str:
    raw = str(value or "").strip()
    if not raw:
        return fallback
    # Consult the label map first so fine-grained inventory tags (клыки, перчатки,
    # fangs, …) collapse into their real category instead of fragmenting the list.
    normalized = raw.casefold().replace(" ", "_")
    if normalized in CATEGORY_RU_LABELS:
        return CATEGORY_RU_LABELS[normalized]
    if any("а" <= ch <= "я" or ch in "ёЁ" for ch in raw.casefold()):
        return raw[:1].upper() + raw[1:]
    return fallback if raw in {"", "None"} else raw


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _format_activity_date(value: Any) -> str:
    """Дата последней активности игрока в формате дд.мм.гг (или «—»)."""
    parsed = _parse_datetime(value)
    if parsed is None:
        return "—"
    return parsed.strftime("%d.%m.%y")


def _admin_panel_ttl_minutes() -> int:
    raw = os.getenv("ADMIN_PANEL_TTL_MINUTES", str(DEFAULT_ADMIN_PANEL_TTL_MINUTES)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_ADMIN_PANEL_TTL_MINUTES
    return max(5, min(value, 24 * 60))


def _session_bucket(data: dict[str, Any]) -> dict[str, Any]:
    sessions = data.setdefault("admin_panel_sessions", {})
    if not isinstance(sessions, dict):
        sessions = {}
        data["admin_panel_sessions"] = sessions
    return sessions


def _new_token(existing: dict[str, Any]) -> str:
    while True:
        token = secrets.token_urlsafe(32)
        if token not in existing:
            return token


def _cleanup_expired_admin_sessions(data: dict[str, Any]) -> int:
    sessions = _session_bucket(data)
    removed = 0
    now = _now()
    for token, session in list(sessions.items()):
        if not isinstance(session, dict):
            sessions.pop(token, None)
            removed += 1
            continue
        expires_at = _parse_datetime(session.get("expires_at"))
        if expires_at is None or expires_at <= now:
            sessions.pop(token, None)
            removed += 1
    return removed


def _save_data(storage: Any, data: dict[str, Any]) -> None:
    if hasattr(storage, "save"):
        storage.save(data)
        return
    raise ValueError("Хранилище не поддерживает сохранение админ-сессий.")


def _storage_supports_admin_sessions(storage: Any) -> bool:
    """Хранилище умеет работать с админ-сессиями точечно, без load()/save().

    Точечные методы критичны для PostgreSQL/SQLite: старый путь load()+save()
    на каждом запросе админ-панели перечитывал и перезаписывал всех игроков,
    что и медленно, и затирает параллельные действия игроков устаревшим
    снапшотом.
    """
    return all(
        callable(getattr(storage, name, None))
        for name in (
            "get_admin_panel_session",
            "put_admin_panel_session",
            "delete_admin_panel_session",
            "delete_admin_panel_sessions_for_admin",
            "cleanup_expired_admin_panel_sessions",
        )
    )


def _new_storage_session_token(storage: Any) -> str:
    while True:
        token = secrets.token_urlsafe(32)
        if storage.get_admin_panel_session(token) is None:
            return token


def create_admin_panel_activation_token(storage: Any, *, platform: str, admin_user_id: str | int, chat_id: str | int | None = None) -> str:
    """Создаёт одноразовый URL-токен админ-панели.

    Новая ссылка для того же админа отключает все старые ссылки и активные
    сессии этого админа. Это защищает от пересланных/забытых ссылок.
    """
    admin_key = f"{platform}:{admin_user_id}"
    now = _now()
    session = {
        "scope": ADMIN_PANEL_SCOPE,
        "kind": "activation",
        "used": False,
        "platform": str(platform),
        "admin_user_id": str(admin_user_id),
        "admin_key": admin_key,
        "chat_id": str(chat_id) if chat_id is not None else "",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=_admin_panel_ttl_minutes())).isoformat(),
    }

    if _storage_supports_admin_sessions(storage):
        storage.cleanup_expired_admin_panel_sessions()
        storage.delete_admin_panel_sessions_for_admin(admin_key, ADMIN_PANEL_SCOPE)
        token = _new_storage_session_token(storage)
        storage.put_admin_panel_session(token, session)
        return token

    data = storage.load()
    sessions = _session_bucket(data)
    _cleanup_expired_admin_sessions(data)
    for old_token, old_session in list(sessions.items()):
        if isinstance(old_session, dict) and old_session.get("admin_key") == admin_key and old_session.get("scope") == ADMIN_PANEL_SCOPE:
            sessions.pop(old_token, None)
    token = _new_token(sessions)
    sessions[token] = session
    _save_data(storage, data)
    return token


def _activated_admin_session(session: dict[str, Any], raw_token: str) -> dict[str, Any]:
    active_session = dict(session)
    active_session.update({
        "kind": "active",
        "used": True,
        "activated_at": _now().isoformat(),
        "activation_token_used": raw_token,
    })
    return active_session


def consume_or_read_admin_session(storage: Any, token: str) -> dict[str, Any] | None:
    raw_token = str(token or "").strip()
    if not raw_token:
        return None

    if _storage_supports_admin_sessions(storage):
        session = storage.get_admin_panel_session(raw_token)
        if not isinstance(session, dict) or session.get("scope") != ADMIN_PANEL_SCOPE:
            return None
        expires_at = _parse_datetime(session.get("expires_at"))
        if expires_at is None or expires_at <= _now():
            storage.delete_admin_panel_session(raw_token)
            return None
        if not bool(session.get("used")):
            active_session = _activated_admin_session(session, raw_token)
            active_token = _new_storage_session_token(storage)
            # Атомарный claim одноразовой ссылки: активную сессию создаёт только
            # запрос, который РЕАЛЬНО удалил токен активации (delete вернул True).
            # Иначе два параллельных запроса по одной ссылке активировали бы её
            # дважды (две активные сессии).
            if not storage.delete_admin_panel_session(raw_token):
                return None
            storage.put_admin_panel_session(active_token, active_session)
            result = dict(active_session)
            result["token"] = active_token
            return result
        result = dict(session)
        result["token"] = raw_token
        return result

    data = storage.load()
    sessions = _session_bucket(data)
    removed = _cleanup_expired_admin_sessions(data)
    session = sessions.get(raw_token)
    if not isinstance(session, dict) or session.get("scope") != ADMIN_PANEL_SCOPE:
        if removed:
            _save_data(storage, data)
        return None
    expires_at = _parse_datetime(session.get("expires_at"))
    if expires_at is None or expires_at <= _now():
        sessions.pop(raw_token, None)
        _save_data(storage, data)
        return None
    if not bool(session.get("used")):
        active_session = _activated_admin_session(session, raw_token)
        active_token = _new_token(sessions)
        sessions.pop(raw_token, None)
        sessions[active_token] = active_session
        _save_data(storage, data)
        result = dict(active_session)
        result["token"] = active_token
        return result
    # Чистое чтение активной сессии ничего не меняет — не сохраняем,
    # чтобы не перезаписывать игроков устаревшим снапшотом.
    if removed:
        _save_data(storage, data)
    result = dict(session)
    result["token"] = raw_token
    return result


def require_admin_session(storage: Any, token: str) -> dict[str, Any]:
    session = consume_or_read_admin_session(storage, token)
    if not session or session.get("kind") != "active":
        raise PermissionError("Админ-сессия недействительна или истекла. Запросите новую ссылку в админ-чате.")
    return session


def _base_url() -> str:
    from services.web_profile import get_site_base_url
    return get_site_base_url()


def build_admin_panel_url(token: str) -> str:
    return f"{_base_url()}/admin_panel?token={token}"


def _item_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("item_id") or "").strip()


def _item_name(item: dict[str, Any]) -> str:
    return str(item.get("name_ru") or item.get("name") or _item_id(item) or "Безымянный предмет").strip()


def _item_category(item: dict[str, Any]) -> str:
    # Prefer the canonical category/type over the inventory-placement labels
    # (category_ru/inventory_section_ru mirror the player's inventory sections —
    # «Клыки», «Рога», «Пояс» — which is "место в инвентаре", not a real category).
    return _category_ru(item.get("category") or item.get("type") or item.get("category_ru") or item.get("inventory_section_ru"), "Прочее")


def _public_icon(item: dict[str, Any]) -> str | None:
    icon = item.get("icon") or item.get("asset_icon") or item.get("asset_path") or item.get("asset_filename") or item.get("image")
    if not icon:
        return None
    text = str(icon).replace("\\", "/").strip()
    if text.startswith("http://") or text.startswith("https://") or text.startswith("/"):
        return text
    if text.startswith("web/public/"):
        text = text[len("web/public"):]
    return "/" + text.lstrip("/")


def _catalog_card(item: dict[str, Any]) -> dict[str, Any]:
    item_id = _item_id(item)
    return {
        "id": item_id,
        "item_id": item_id,
        "kind": "item",
        "name": _item_name(item),
        "category": _item_category(item),
        "icon": _public_icon(item),
        "description": str(item.get("description") or item.get("short_description") or "Описание предмета пока не добавлено."),
        "stackable": bool(item.get("stackable", True)),
        "max_stack": _safe_int(item.get("max_stack") or item.get("stack_size"), 1),
    }


@lru_cache(maxsize=1)
def _catalog_cards_cache() -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    """Build catalog cards once and reuse them across requests.

    Rebuilding ~150 cards on every admin keystroke is wasteful. The cache is
    cleared together with the item registry (see invalidate_admin_catalog_cache),
    so an admin icon change is still reflected immediately.
    """
    synthetic = tuple(dict(value) for value in SYNTHETIC_REWARD_IDS.values())
    definitions = tuple(
        _catalog_card(item)
        for item in load_all_item_definitions()
        if _item_id(item) and _item_id(item) not in HIDDEN_CATALOG_ITEM_IDS
    )
    return synthetic, definitions


def invalidate_admin_catalog_cache() -> None:
    _catalog_cards_cache.cache_clear()


def admin_catalog(*, query: str = "", category: str = "") -> dict[str, Any]:
    synthetic_t, definitions_t = _catalog_cards_cache()
    synthetic = [dict(card) for card in synthetic_t]
    definitions = [dict(card) for card in definitions_t]
    cards = synthetic + definitions
    query_cf = str(query or "").strip().casefold()
    category_cf = str(category or "").strip().casefold()
    if query_cf:
        cards = [card for card in cards if query_cf in str(card.get("name") or "").casefold() or query_cf in str(card.get("item_id") or "").casefold()]
    if category_cf:
        cards = [card for card in cards if category_cf == str(card.get("category") or "").casefold()]
    cards.sort(key=lambda card: (str(card.get("category") or ""), str(card.get("name") or "")))
    categories = sorted({str(card.get("category") or "Прочее") for card in synthetic + definitions})
    return {"items": cards, "categories": categories, "syntheticRewardIds": sorted(SYNTHETIC_REWARD_IDS)}


def admin_catalog_item(item_id: str) -> dict[str, Any] | None:
    cleaned = str(item_id or "").strip()
    if cleaned in SYNTHETIC_REWARD_IDS:
        item = dict(SYNTHETIC_REWARD_IDS[cleaned])
        item["full_description"] = item["description"]
        return item
    if cleaned in HIDDEN_CATALOG_ITEM_IDS:
        return None
    definition = get_item_definition_by_id(cleaned)
    if not definition:
        return None
    result = deepcopy(definition)
    result.update(_catalog_card(definition))
    result["raw"] = definition
    result["formulas"] = _collect_formula_fields(definition)
    result["sources_text"] = _collect_sources_text(definition)
    result["needs_text"] = _collect_needs_text(definition)
    return result


def _collect_formula_fields(value: Any, prefix: str = "") -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            key_cf = str(key).casefold()
            if "formula" in key_cf or "формул" in key_cf:
                result.append({"field": path, "value": json.dumps(nested, ensure_ascii=False) if not isinstance(nested, str) else nested})
            result.extend(_collect_formula_fields(nested, path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            result.extend(_collect_formula_fields(nested, f"{prefix}[{index}]"))
    return result[:50]


def _collect_sources_text(item: dict[str, Any]) -> str:
    fields = ["source", "sources", "found_in", "location", "locations", "drop_from", "crafting_station", "market", "buy_source"]
    values: list[str] = []
    for field in fields:
        value = item.get(field)
        if not value:
            continue
        if isinstance(value, (list, tuple)):
            values.extend(str(part) for part in value if part)
        else:
            values.append(str(value))
    return "; ".join(dict.fromkeys(values)) or "Источник не указан."


def _collect_needs_text(item: dict[str, Any]) -> str:
    fields = ["purpose", "used_for", "needed_for", "crafting_use", "description"]
    values: list[str] = []
    for field in fields:
        value = item.get(field)
        if value:
            values.append(str(value))
    return "; ".join(dict.fromkeys(values)) or "Назначение не указано."


def list_admin_players(storage: Any, *, query: str = "", limit: int = 200) -> list[dict[str, Any]]:
    if query:
        # find_players уже использует быстрые точечные методы и ищет в т.ч. по
        # Telegram/VK id, поэтому оставляем его на путь поиска.
        players = find_players(storage, query, limit=limit)
    elif callable(getattr(storage, "list_admin_player_cards", None)):
        # Просмотр всех: лёгкий путь без чтения полных профилей всех игроков.
        return storage.list_admin_player_cards(query="", limit=limit)
    else:
        data = storage.load()
        players = [player for player in (data.get("players") or {}).values() if isinstance(player, dict)]
    cards = []
    for player in players:
        cards.append({
            "game_id": player.get("game_id") or player.get("id"),
            "name": player.get("name") or "без имени",
            "level": _safe_int(player.get("level"), 1),
            "public_id": player.get("public_id"),
            "last_activity": _format_activity_date(player.get("last_activity_at")),
        })
    cards.sort(key=lambda item: (str(item.get("name") or "").casefold(), str(item.get("game_id") or "")))
    return cards[:max(1, min(int(limit), 1000))]


def admin_player_detail(storage: Any, game_id: str) -> dict[str, Any] | None:
    player = storage.get_player_by_game_id(normalize_game_id(game_id)) if hasattr(storage, "get_player_by_game_id") else None
    if not player:
        return None
    return {
        "summary": format_player_admin_summary(player),
        "game_id": player.get("game_id") or player.get("id"),
        "name": player.get("name"),
        "level": _safe_int(player.get("level"), 1),
        "experience": _safe_int(player.get("experience"), 0),
        "money": _safe_int(player.get("money_copper", player.get("money", 0)), 0),
        "free_stat_points": _safe_int(player.get("free_stat_points"), 0),
        "free_skill_points": _safe_int(player.get("free_skill_points"), 0),
        "location": player.get("location_id") or player.get("current_zone") or player.get("current_city"),
        "last_activity": _format_activity_date(player.get("last_activity_at")),
    }


def _normalize_rewards(rewards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for reward in rewards or []:
        if not isinstance(reward, dict):
            continue
        item_id = str(reward.get("item_id") or reward.get("id") or "").strip()
        amount = _safe_int(reward.get("amount"), 0)
        if not item_id or amount <= 0:
            continue
        if amount > MAX_REWARD_AMOUNT:
            raise ValueError("Слишком большое количество в одной позиции награды.")
        if item_id in SYNTHETIC_REWARD_IDS:
            kind = SYNTHETIC_REWARD_IDS[item_id]["kind"]
            if kind == "money":
                per_unit = _safe_int(SYNTHETIC_REWARD_IDS[item_id].get("copper_per_unit"), 1) or 1
                if amount * per_unit > MAX_REWARD_MONEY_COPPER:
                    raise ValueError("Слишком большая сумма награды (превышает лимит в медном эквиваленте).")
        else:
            kind = "item"
            if get_item_definition_by_id(item_id) is None:
                raise ValueError(f"Предмет {item_id} не найден в каталоге.")
        normalized.append({"item_id": item_id, "amount": amount, "kind": kind})
    if not normalized:
        raise ValueError("Список наград пустой.")
    return normalized


def _apply_rewards_to_player(player: dict[str, Any], rewards: list[dict[str, Any]], *, source: str) -> list[str]:
    lines: list[str] = []
    for reward in rewards:
        item_id = reward["item_id"]
        amount = reward["amount"]
        kind = reward["kind"]
        if kind == "money":
            per_unit = _safe_int(SYNTHETIC_REWARD_IDS.get(item_id, {}).get("copper_per_unit"), 1) or 1
            delta = amount * per_unit
            old_money = _safe_int(player.get("money_copper", player.get("money", 0)), 0)
            new_money = max(0, old_money + delta)
            player["money_copper"] = new_money
            player["money"] = new_money
            coin_name = SYNTHETIC_REWARD_IDS.get(item_id, {}).get("name", "Медные монеты")
            lines.append(f"{coin_name} ×{amount}")
        elif kind == "skill_points":
            player["free_skill_points"] = _safe_int(player.get("free_skill_points"), 0) + amount
            lines.append(f"Очки навыков ×{amount}")
        elif kind == "stat_points":
            player["free_stat_points"] = _safe_int(player.get("free_stat_points"), 0) + amount
            lines.append(f"Очки характеристик ×{amount}")
        elif kind == "experience":
            grant_exact_experience(player, amount)
            lines.append(f"Крупицы опыта ×{amount}")
        else:
            definition = get_item_definition_by_id(item_id)
            item = registry_item_to_inventory_item(definition, amount) if definition else build_inventory_item(item_id, amount, item_id=item_id)
            item["source"] = source
            result = add_inventory_item(player, item, amount, default_source=source)
            if result.added <= 0:
                raise ValueError(f"У игрока нет места для предмета {item_id}.")
            name = item.get("name") or item.get("name_ru") or item_id
            lines.append(f"{name} ×{result.added}")
    recalculate_inventory_overflow(player)
    return lines


def deliver_rewards_to_player(storage: Any, *, target_game_id: str, rewards: list[dict[str, Any]], admin_session: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_rewards(rewards)
    game_id = normalize_game_id(target_game_id)
    player = storage.get_player_by_game_id(game_id) if hasattr(storage, "get_player_by_game_id") else None
    if not player:
        raise ValueError(f"Игрок {game_id} не найден.")
    backup_player(player, "before_admin_panel_delivery")
    lines = _apply_rewards_to_player(player, normalized, source="admin_panel_delivery")
    text = "Вы получили в дар от высших сил:\n" + "\n".join(f"• {line}" for line in lines)
    storage.update_player(player)
    # Сообщение игроку — через атомарный outbox, чтобы пересохранение игрока
    # ботом не затёрло его (lost update).
    gift_message = {
        "type": "admin_gift",
        "text": text,
        "created_at": _now().isoformat(),
        "source": "admin_panel",
    }
    enqueue = getattr(storage, "enqueue_bot_messages", None)
    if callable(enqueue):
        enqueue(game_id, [gift_message])
    else:  # запасной путь для хранилищ без атомарного outbox
        player.setdefault("pending_bot_messages", []).append(gift_message)
        storage.update_player(player)
    write_admin_audit(
        platform=str(admin_session.get("platform") or "admin_panel"),
        admin_user_id=str(admin_session.get("admin_user_id") or "unknown"),
        command="admin_panel_delivery",
        action="admin_panel_delivery",
        details={"target_game_id": game_id, "rewards": normalized},
    )
    return {"ok": True, "target_game_id": game_id, "delivered": lines, "playerMessageQueued": True}


def rewards_to_promo_payload(rewards: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = _normalize_rewards(rewards)
    payload: dict[str, Any] = {"items": []}
    for reward in normalized:
        item_id = reward["item_id"]
        amount = reward["amount"]
        kind = reward["kind"]
        if kind == "money":
            per_unit = _safe_int(SYNTHETIC_REWARD_IDS.get(item_id, {}).get("copper_per_unit"), 1) or 1
            payload["money"] = _safe_int(payload.get("money"), 0) + amount * per_unit
        elif kind == "skill_points":
            payload["free_skill_points"] = _safe_int(payload.get("free_skill_points"), 0) + amount
        elif kind == "stat_points":
            payload["free_stat_points"] = _safe_int(payload.get("free_stat_points"), 0) + amount
        elif kind == "experience":
            payload["experience"] = _safe_int(payload.get("experience"), 0) + amount
        else:
            payload.setdefault("items", []).append({"item_id": item_id, "amount": amount})
    if not payload.get("items"):
        payload.pop("items", None)
    return payload


def duration_to_expires_at(duration: str | None) -> str | None:
    value = str(duration or "never").strip().casefold()
    if value in {"never", "forever", "бессрочный", "бессрочно", "none", ""}:
        return None
    mapping = {
        "1h": timedelta(hours=1),
        "1_hour": timedelta(hours=1),
        "1 час": timedelta(hours=1),
        "12h": timedelta(hours=12),
        "12_hours": timedelta(hours=12),
        "12 часов": timedelta(hours=12),
        "1d": timedelta(days=1),
        "1_day": timedelta(days=1),
        "1 день": timedelta(days=1),
        "7d": timedelta(days=7),
        "7_days": timedelta(days=7),
        "7 дней": timedelta(days=7),
        "30d": timedelta(days=30),
        "30_days": timedelta(days=30),
        "30 дней": timedelta(days=30),
        "365d": timedelta(days=365),
        "365_days": timedelta(days=365),
        "365 дней": timedelta(days=365),
    }
    delta = mapping.get(value)
    if delta is None:
        raise ValueError("Неизвестное время жизни промокода.")
    return (_now() + delta).isoformat()


def create_admin_promo(storage: Any, *, code: str, uses_left: int, duration: str | None, rewards: list[dict[str, Any]], admin_session: dict[str, Any]) -> dict[str, Any]:
    reward_payload = rewards_to_promo_payload(rewards)
    expires_at = duration_to_expires_at(duration)
    promo = add_promo_code(code=code, uses_left=int(uses_left), reward=reward_payload, expires_at=expires_at, storage=storage)
    write_admin_audit(
        platform=str(admin_session.get("platform") or "admin_panel"),
        admin_user_id=str(admin_session.get("admin_user_id") or "unknown"),
        command="admin_panel_promo_create",
        action="admin_panel_promo_create",
        details={"code": promo.get("code"), "uses_left": uses_left, "expires_at": expires_at, "reward": reward_payload},
    )
    return promo




def delete_admin_promo(storage: Any, *, code: str, admin_session: dict[str, Any]) -> bool:
    ok = delete_promo_code(code, storage=storage)
    if ok:
        write_admin_audit(
            platform=str(admin_session.get("platform") or "admin_panel"),
            admin_user_id=str(admin_session.get("admin_user_id") or "unknown"),
            command="admin_panel_promo_delete",
            action="admin_panel_promo_delete",
            details={"code": str(code or "")},
        )
    return ok

def promo_list_payload(storage: Any) -> list[dict[str, Any]]:
    data = load_promo_data(storage)
    promos = list((data.get("codes") or {}).values())
    promos.sort(key=lambda promo: str(promo.get("created_at") or ""), reverse=True)
    now = _now()
    result: list[dict[str, Any]] = []
    for promo in promos:
        expires = _parse_datetime(promo.get("expires_at"))
        seconds_left = None if expires is None else max(0, int((expires - now).total_seconds()))
        uses_left = _safe_int(promo.get("uses_left"), 0)
        used_count = len(promo.get("used_by") or []) if isinstance(promo.get("used_by"), list) else 0
        result.append({
            "code": promo.get("code"),
            "active": bool(promo.get("active")),
            "created_at": promo.get("created_at"),
            "expires_at": promo.get("expires_at"),
            "seconds_left": seconds_left,
            "uses_left": uses_left,
            "used_count": used_count,
            "reward": promo.get("reward") or {},
            "one_use_per_player": bool(promo.get("one_use_per_player", True)),
        })
    return result


def create_admin_player_view_token(storage: Any, *, target_game_id: str, admin_session: dict[str, Any]) -> str:
    game_id = normalize_game_id(target_game_id)
    if not hasattr(storage, "get_player_by_game_id") or storage.get_player_by_game_id(game_id) is None:
        raise ValueError(f"Игрок {game_id} не найден.")
    now = _now()
    session = {
        "scope": ADMIN_PLAYER_VIEW_SCOPE,
        "kind": "active",
        "used": True,
        "platform": str(admin_session.get("platform") or "admin_panel"),
        "admin_user_id": str(admin_session.get("admin_user_id") or "unknown"),
        "admin_key": str(admin_session.get("admin_key") or ""),
        "target_game_id": game_id,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=ADMIN_PLAYER_VIEW_TTL_MINUTES)).isoformat(),
    }
    if _storage_supports_admin_sessions(storage):
        storage.cleanup_expired_admin_panel_sessions()
        token = _new_storage_session_token(storage)
        storage.put_admin_panel_session(token, session)
        return token
    data = storage.load()
    sessions = _session_bucket(data)
    _cleanup_expired_admin_sessions(data)
    token = _new_token(sessions)
    sessions[token] = session
    _save_data(storage, data)
    return token


def get_admin_player_view_profile(storage: Any, token: str) -> dict[str, Any] | None:
    raw_token = str(token or "")

    if _storage_supports_admin_sessions(storage):
        session = storage.get_admin_panel_session(raw_token)
        if not isinstance(session, dict) or session.get("scope") != ADMIN_PLAYER_VIEW_SCOPE:
            return None
        expires_at = _parse_datetime(session.get("expires_at"))
        if expires_at is None or expires_at <= _now():
            storage.delete_admin_panel_session(raw_token)
            return None
    else:
        data = storage.load()
        sessions = _session_bucket(data)
        removed = _cleanup_expired_admin_sessions(data)
        session = sessions.get(raw_token)
        if not isinstance(session, dict) or session.get("scope") != ADMIN_PLAYER_VIEW_SCOPE:
            if removed:
                _save_data(storage, data)
            return None
        expires_at = _parse_datetime(session.get("expires_at"))
        if expires_at is None or expires_at <= _now():
            sessions.pop(raw_token, None)
            _save_data(storage, data)
            return None
        if removed:
            _save_data(storage, data)

    target_game_id = str(session.get("target_game_id") or "")
    player = storage.get_player_by_game_id(target_game_id) if hasattr(storage, "get_player_by_game_id") else None
    if not player:
        return None
    from site_api import frontend_profile
    profile = frontend_profile(player)
    # Админ заходит в чужой профиль с правом редактирования (как игрок) плюс
    # отдельная кнопка «удалить из профиля игрока». Право даётся через обычный
    # профильный веб-токен этого игрока — все существующие профильные эндпоинты
    # работают без дублирования логики.
    profile["adminView"] = True
    profile["adminEdit"] = True
    edit_token = ""
    try:
        from services.web_profile import ADMIN_PROFILE_EDIT_SCOPE
        # Отдельный scope + короткий TTL (как окно просмотра): не разлогинивает
        # игрока (его PROFILE-сессия не трогается) и не оставляет долгоживущего
        # доступа после закрытия окна просмотра.
        platform = str(session.get("platform") or "admin_panel")
        if hasattr(storage, "create_web_session"):
            edit_token = storage.create_web_session(
                game_id=target_game_id,
                scope=ADMIN_PROFILE_EDIT_SCOPE,
                platform=platform,
                lifetime_minutes=ADMIN_PLAYER_VIEW_TTL_MINUTES,
            )
    except Exception:
        edit_token = ""
    if edit_token:
        try:
            write_admin_audit(
                platform=str(session.get("platform") or "admin_panel"),
                admin_user_id=str(session.get("admin_user_id") or "unknown"),
                command="admin_panel_edit_profile_session",
                action="admin_panel_edit_profile_session",
                details={"target_game_id": target_game_id},
            )
        except Exception:
            pass
    return {
        "profile": profile,
        "editToken": edit_token,
        "session": {"expires_at": session.get("expires_at"), "target_game_id": session.get("target_game_id")},
    }


def _uploaded_image_format(blob: bytes) -> str | None:
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if blob.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if len(blob) >= 12 and blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "WEBP"
    return None


def _normalize_uploaded_image(blob: bytes) -> tuple[bytes, str, str]:
    if _uploaded_image_format(blob) is None:
        raise ValueError("Файл не похож на PNG, JPG или WebP по сигнатуре.")
    try:
        with Image.open(io.BytesIO(blob)) as probe:
            fmt = str(probe.format or "").upper()
            width, height = probe.size
            probe.verify()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise ValueError("Файл изображения повреждён или имеет неподдерживаемый формат.") from exc
    if fmt not in {"PNG", "JPEG", "WEBP"}:
        raise ValueError("Поддерживаются только PNG, JPG/JPEG и WebP.")
    if width < 1 or height < 1 or width > 4096 or height > 4096 or width * height > 16_777_216:
        raise ValueError("Размер изображения должен быть от 1×1 до 4096×4096 и не больше 16 Мп.")
    try:
        with Image.open(io.BytesIO(blob)) as image:
            output = io.BytesIO()
            if fmt == "JPEG":
                normalized = image.convert("RGB")
                normalized.save(output, format="JPEG", quality=90, optimize=True)
                return output.getvalue(), ".jpg", "image/jpeg"
            if fmt == "WEBP":
                normalized = image.convert("RGBA")
                normalized.save(output, format="WEBP", quality=90, method=6)
                return output.getvalue(), ".webp", "image/webp"
            normalized = image.convert("RGBA")
            normalized.save(output, format="PNG", optimize=True)
            return output.getvalue(), ".png", "image/png"
    except (OSError, ValueError) as exc:
        raise ValueError("Не удалось нормализовать изображение перед сохранением.") from exc


def _runtime_upload_target(relative_public_path: str) -> Path:
    cleaned = relative_public_path.lstrip("/")
    if not cleaned.startswith("assets/admin_uploads/"):
        raise ValueError("Runtime upload path must be inside assets/admin_uploads.")
    relative_under_assets = cleaned.removeprefix("assets/")
    return resolve_project_path(PUBLIC_UPLOADS_ASSETS_DIR) / relative_under_assets


def update_item_image_from_base64(storage: Any, *, item_id: str, filename: str, content_base64: str, content_type: str | None, admin_session: dict[str, Any]) -> dict[str, Any]:
    cleaned_item_id = str(item_id or "").strip()
    if not cleaned_item_id or cleaned_item_id in SYNTHETIC_REWARD_IDS:
        raise ValueError("Изображение можно менять только у игровых предметов.")
    if get_item_definition_by_id(cleaned_item_id) is None:
        raise ValueError(f"Предмет {cleaned_item_id} не найден.")
    raw = str(content_base64 or "")
    if "," in raw and raw.strip().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        blob = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Файл должен быть передан в base64.") from exc
    if not blob or len(blob) > 8 * 1024 * 1024:
        raise ValueError("Файл пустой или больше 8 МБ.")
    normalized_blob, suffix, normalized_content_type = _normalize_uploaded_image(blob)
    safe_item_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", cleaned_item_id)[:80]
    rel_public = f"/assets/admin_uploads/items/{safe_item_id}{suffix}"
    target_path = _runtime_upload_target(rel_public)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(normalized_blob)

    # Durable source of truth lives in the uploads volume, not in data/*.json
    # (those are baked into the image and reset on every container rebuild).
    # Pin the overrides file to the same uploads dir we just wrote the image to,
    # so it shares the persistent volume (and test redirects stay isolated).
    from services.item_registry import set_icon_override

    overrides_path = resolve_project_path(PUBLIC_UPLOADS_ASSETS_DIR) / "admin_uploads" / "icon_overrides.json"
    set_icon_override(cleaned_item_id, rel_public, overrides_path=overrides_path)

    # Player inventories are stored in the DB volume, so existing copies of the
    # item still need their icon refreshed once.
    if hasattr(storage, "load") and hasattr(storage, "save"):
        data = storage.load()
        player_changes = 0
        for player in (data.get("players") or {}).values():
            if isinstance(player, dict) and _replace_item_icon_in_payload(player, cleaned_item_id, rel_public):
                player_changes += 1
        if player_changes:
            storage.save(data)
    write_admin_audit(
        platform=str(admin_session.get("platform") or "admin_panel"),
        admin_user_id=str(admin_session.get("admin_user_id") or "unknown"),
        command="admin_panel_change_item_image",
        action="admin_panel_change_item_image",
        details={"item_id": cleaned_item_id, "asset_path": rel_public, "persisted": "icon_overrides"},
    )
    return {"ok": True, "item_id": cleaned_item_id, "asset_path": rel_public, "content_type": normalized_content_type, "changed_files": []}


def _replace_item_icon_in_payload(value: Any, item_id: str, new_path: str) -> int:
    changed = 0
    if isinstance(value, dict):
        current_id = str(value.get("item_id") or value.get("id") or "").strip()
        if current_id == item_id:
            for key in ("icon", "asset_icon", "asset_path", "asset_filename", "image"):
                if key in value or key in {"icon", "asset_path"}:
                    if value.get(key) != new_path:
                        value[key] = new_path
                        changed += 1
        for nested in value.values():
            changed += _replace_item_icon_in_payload(nested, item_id, new_path)
    elif isinstance(value, list):
        for nested in value:
            changed += _replace_item_icon_in_payload(nested, item_id, new_path)
    return changed


def player_logs_last_24h(storage: Any, *, game_id: str, limit: int = 200) -> list[dict[str, Any]]:
    normalized = normalize_game_id(game_id)
    data = storage.load() if hasattr(storage, "load") else {}
    player = (data.get("players") or {}).get(normalized)
    logs: list[dict[str, Any]] = []
    if isinstance(player, dict):
        for key in ("action_log", "chat_log", "bot_log", "admin_pending_messages", "pending_bot_messages"):
            value = player.get(key)
            if isinstance(value, list):
                for entry in value[-limit:]:
                    logs.append({"source": key, "entry": entry})
    # Глобальный audit log полезен для админа, но фильтруем только строки где есть game_id.
    audit_path = resolve_project_path("data/admin_audit.log")
    if audit_path.exists():
        try:
            for line in audit_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-1000:]:
                if normalized in line:
                    logs.append({"source": "admin_audit", "entry": line})
        except Exception:
            pass
    return logs[-max(1, min(limit, 500)):]


def player_chat_last_24h(storage: Any, *, game_id: str, limit: int = 200) -> list[dict[str, Any]]:
    normalized = normalize_game_id(game_id)
    data = storage.load() if hasattr(storage, "load") else {}
    player = (data.get("players") or {}).get(normalized)
    logs: list[dict[str, Any]] = []
    if isinstance(player, dict):
        value = player.get("chat_log")
        if isinstance(value, list):
            logs.extend(entry for entry in value[-limit:] if isinstance(entry, dict))
        # До появления полноценного chat_log показываем очередь сообщений бота как часть переписки.
        pending = player.get("pending_bot_messages")
        if isinstance(pending, list):
            for entry in pending[-limit:]:
                logs.append({"direction": "bot_pending", "text": entry.get("text") if isinstance(entry, dict) else str(entry), "created_at": entry.get("created_at") if isinstance(entry, dict) else ""})
    return logs[-max(1, min(limit, 500)):]
