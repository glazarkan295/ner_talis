"""Конструктор города и крепости V2 (ТЗ §4–§6) — система узлов.

Город и крепость редактируются как система УЗЛОВ: узел (city_node) — любая точка
структуры (город/квартал/здание/ратуша/рынок/застава/причал/таверна/криминальная
зона/переход/…). К узлам привязываются под-объекты: кнопки (city_button §4.3),
товары торговых точек (city_shop_item §4.4), ремесленные/алхимические сервисы
(city_service §4.5) и криминальные зоны (criminal_zone §4.6). Связи по parent_id
дают дерево (визуализация §5).

Это слой данных + валидация; рантайм города/крепости (city_service навигация,
external_location_service) — отдельная подсистема. Хранение — генерик EntityStore
(data/city_constructor.json) с тегом _kind. Аудит и права (city.*) — в роутере
admin_city_api.
"""

from __future__ import annotations

import re
from typing import Any, Callable

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

# --- Типы объектов ----------------------------------------------------------
KIND_NODE = "city_node"
KIND_BUTTON = "city_button"
KIND_SHOP_ITEM = "city_shop_item"
KIND_SERVICE = "city_service"
KIND_CRIMINAL = "criminal_zone"
KINDS = (KIND_NODE, KIND_BUTTON, KIND_SHOP_ITEM, KIND_SERVICE, KIND_CRIMINAL)

# Типы узлов (§4.2).
NODE_TYPES = (
    "city", "fortress", "quarter", "district", "square", "street", "alley",
    "building", "townhall", "market", "workshop", "tavern", "pier", "outpost",
    "stand", "board", "criminal_zone", "residential", "service", "transition",
)
# Действия кнопок (§4.3).
BUTTON_ACTIONS = (
    "goto_node", "open_market", "open_npc", "open_quests", "open_craft",
    "open_alchemy", "start_fishing", "open_fines", "open_board", "start_event",
    "go_back", "show_message",
)
# Торговые точки (§4.4).
SHOP_KINDS = (
    "city_market", "port_market", "trade_quarter", "black_market",
    "resource_buyer", "npc_trader", "temp_trader", "event_trader", "fortress_supplier",
)
# Ремесленные сервисы (§4.5).
SERVICE_KINDS = ("smelter", "forge", "leatherworks", "alchemy", "jewelry", "enchanting")
CURRENCIES = ("copper", "silver", "gold", "magic_gold", "ancient")
# Тип доступа стока товара (§4.4).
STOCK_TYPES = ("always", "conditional", "event_only")

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{1,63}$")
_HTML_RE = re.compile(r"<[^>]+>")

_store = EntityStore(
    env_var="CITY_CONSTRUCTOR_PATH",
    default_rel="data/city_constructor.json",
    statuses=STATUSES,
    transitions=TRANSITIONS,
    initial_status=STATUS_DRAFT,
)


def store() -> EntityStore:
    return _store


def _str(data: dict[str, Any], key: str) -> str:
    return str(data.get(key) or "").strip()


def _has_markup(value: str) -> bool:
    low = value.lower()
    return "<script" in low or bool(_HTML_RE.search(value))


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _markup_errors(data: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for key in keys:
        value = _str(data, key)
        if value and _has_markup(value):
            out.append(f"В поле «{key}» недопустим HTML.")
    return out


def _validate_node(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []
    if not _str(data, "name"):
        errors.append("Не заполнено название узла.")
    node_type = _str(data, "node_type")
    if not node_type:
        errors.append("Не выбран тип узла.")
    elif node_type not in NODE_TYPES:
        errors.append(f"Неизвестный тип узла: {node_type}.")
    errors += _markup_errors(data, ("name", "short_description", "description"))
    order = data.get("order")
    if order not in (None, "") and _num(order) is None:
        errors.append("Порядок отображения — не число.")
    if node_type not in ("city", "fortress") and not _str(data, "parent_id"):
        warnings.append("У узла не указан родительский узел (parent_id).")
    # Вывод сообщения игроку при входе в узел (дополнение к ТЗ): формат/блоки/лимиты.
    msg = data.get("entry_message")
    if msg:
        from services.message_output_service import validate_message_output
        result = validate_message_output(msg)
        errors += [f"Сообщение при входе — {e}" for e in result["errors"]]
        warnings += [f"Сообщение при входе — {w}" for w in result["warnings"]]
    return errors, warnings


def _validate_button(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []
    if not _str(data, "label"):
        errors.append("Не заполнен текст кнопки.")
    action = _str(data, "action")
    if not action:
        errors.append("Не выбрано действие кнопки.")
    elif action not in BUTTON_ACTIONS:
        errors.append(f"Неизвестное действие кнопки: {action}.")
    if not _str(data, "node_id"):
        warnings.append("Кнопка не привязана к узлу (node_id).")
    if action in ("goto_node",) and not _str(data, "target_node_id"):
        errors.append("Для перехода укажите целевой узел (target_node_id).")
    for key in ("cost", "energy_cost"):
        value = data.get(key)
        if value not in (None, ""):
            num = _num(value)
            if num is None:
                errors.append(f"Поле «{key}» — не число.")
            elif num < 0:
                errors.append(f"Поле «{key}» не может быть отрицательным.")
    errors += _markup_errors(data, ("label", "success_text", "denied_text"))
    return errors, warnings


def _validate_shop_item(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []
    if not _str(data, "item_id"):
        errors.append("Не указан предмет (item_id).")
    shop_kind = _str(data, "shop_kind")
    if shop_kind and shop_kind not in SHOP_KINDS:
        errors.append(f"Неизвестная торговая точка: {shop_kind}.")
    currency = _str(data, "currency") or "copper"
    if currency not in CURRENCIES:
        errors.append(f"Неизвестная валюта: {currency}.")
    stock_type = _str(data, "stock_type")
    if stock_type and stock_type not in STOCK_TYPES:
        errors.append(f"Неизвестный тип стока: {stock_type}.")
    for key in ("price_buy", "price_sell", "stock", "per_player_limit", "daily_limit", "weekly_limit"):
        value = data.get(key)
        if value in (None, ""):
            continue
        num = _num(value)
        if num is None:
            errors.append(f"Поле «{key}» — не число.")
        elif num < 0:
            errors.append(f"Поле «{key}» не может быть отрицательным.")
    chance = data.get("appear_chance")
    if chance not in (None, ""):
        num = _num(chance)
        if num is None or num < 0 or num > 100:
            errors.append("Шанс появления должен быть 0–100.")
    if not data.get("can_buy") and not data.get("can_sell"):
        warnings.append("Товар нельзя ни купить, ни продать — отметьте «можно купить» или «можно продать».")
    return errors, warnings


def _validate_service(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    if not _str(data, "name"):
        errors.append("Не заполнено название сервиса.")
    service_kind = _str(data, "service_kind")
    if not service_kind:
        errors.append("Не выбран тип сервиса.")
    elif service_kind not in SERVICE_KINDS:
        errors.append(f"Неизвестный тип сервиса: {service_kind}.")
    for key in ("craft_time", "cost", "success_chance", "upgrade_chance"):
        value = data.get(key)
        if value in (None, ""):
            continue
        num = _num(value)
        if num is None:
            errors.append(f"Поле «{key}» — не число.")
        elif num < 0:
            errors.append(f"Поле «{key}» не может быть отрицательным.")
    for key in ("success_chance", "upgrade_chance"):
        value = data.get(key)
        if value not in (None, "") and (_num(value) or 0) > 100:
            errors.append(f"Поле «{key}» должно быть 0–100.")
    errors += _markup_errors(data, ("name", "description"))
    return errors, []


def _validate_criminal(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    if not _str(data, "name"):
        errors.append("Не заполнено название криминальной зоны.")
    raid = data.get("raid_chance")
    if raid not in (None, ""):
        num = _num(raid)
        if num is None or num < 0 or num > 100:
            errors.append("Шанс облавы должен быть 0–100.")
    for key in ("fine_amount", "fine_deadline_days"):
        value = data.get(key)
        if value in (None, ""):
            continue
        num = _num(value)
        if num is None:
            errors.append(f"Поле «{key}» — не число.")
        elif num < 0:
            errors.append(f"Поле «{key}» не может быть отрицательным.")
    errors += _markup_errors(data, ("name", "enter_text", "raid_text", "success_text", "fail_text"))
    return errors, []


VALIDATORS: dict[str, Callable[[dict[str, Any]], tuple[list[str], list[str]]]] = {
    KIND_NODE: _validate_node,
    KIND_BUTTON: _validate_button,
    KIND_SHOP_ITEM: _validate_shop_item,
    KIND_SERVICE: _validate_service,
    KIND_CRIMINAL: _validate_criminal,
}


def validate(kind: str, envelope: dict[str, Any]) -> dict[str, Any]:
    validator = VALIDATORS.get(kind)
    if validator is None:
        return {"ok": False, "errors": [f"Неизвестный тип объекта: {kind}."], "warnings": []}
    errors, warnings = validator(envelope)
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def build_tree() -> list[dict[str, Any]]:
    """Дерево узлов по parent_id (визуализация §5). Корни — city/fortress/без родителя."""
    nodes = [i for i in _store.list() if (i.get("data") or {}).get("_kind") == KIND_NODE]
    by_id = {n["id"]: n for n in nodes}
    children: dict[str, list[str]] = {}
    roots: list[str] = []
    for node in nodes:
        parent = str((node.get("data") or {}).get("parent_id") or "")
        if parent and parent in by_id:
            children.setdefault(parent, []).append(node["id"])
        else:
            roots.append(node["id"])

    def _order(node_id: str) -> tuple[float, str]:
        data = by_id[node_id].get("data") or {}
        return (_num(data.get("order")) or 0.0, str(data.get("name") or node_id))

    def _node(node_id: str, depth: int) -> dict[str, Any]:
        env = by_id[node_id]
        data = env.get("data") or {}
        kids = sorted(children.get(node_id, []), key=_order)
        return {
            "id": node_id,
            "name": data.get("name") or node_id,
            "node_type": data.get("node_type") or "",
            "status": env.get("status"),
            "depth": depth,
            "children": [_node(child, depth + 1) for child in kids],
        }

    return [_node(rid, 0) for rid in sorted(roots, key=_order)]
