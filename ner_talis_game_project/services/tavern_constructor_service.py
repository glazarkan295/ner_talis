"""Конструктор таверны (ТЗ таверны).

Таверна = отдельная сущность с вложенными коллекциями: услуги, меню, отдых,
слухи, связи NPC, события, правила репутации, риски, расписание, кнопки и
тексты. Хранение — EntityStore (data/tavern_constructor.json). Слой данных +
валидация + предпросмотр; рантайм-методы бота — на вырост.

UX: формулы цен игроку не показываем — только итоговая цена и понятные тексты.
"""

from __future__ import annotations

import math
import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")

TAVERN_TYPES = (
    "city_tavern", "fortress_tavern", "road_tavern", "port_tavern",
    "guild_tavern", "hidden_tavern", "event_tavern", "temporary_tavern",
)
TAVERN_TYPE_LABELS = {
    "city_tavern": "Городская", "fortress_tavern": "Крепости", "road_tavern": "Дорожная",
    "port_tavern": "Портовая", "guild_tavern": "Гильдейская", "hidden_tavern": "Скрытая",
    "event_tavern": "Событийная", "temporary_tavern": "Временная",
}
TAVERN_MODES = ("active", "hidden", "disabled", "event_only", "admin_only")
SERVICE_TYPES = ("food", "drink", "rest", "room", "rumor", "quest", "hire", "npc", "event", "hidden", "custom")
MENU_CATEGORIES = ("food", "drink", "special", "seasonal", "hidden")
RUMOR_TYPES = (
    "common", "location", "resource", "mob", "boss", "quest", "npc", "market",
    "crime", "ancient", "false", "hidden", "event",
)
EVENT_TYPES = (
    "npc_meeting", "brawl", "rumor", "discount", "rare_menu", "guard_check",
    "crime", "festival", "duel", "loss", "find", "quest", "attack",
)
RISK_TYPES = (
    "coin_loss", "brawl", "trauma", "fine", "raid", "reputation_loss",
    "addiction", "tolerance", "negative_effect", "item_loss", "ambush",
    "false_rumor", "service_block", "ban",
)
SCHEDULE_MODES = ("always", "day", "night", "weekly", "seasonal", "event", "custom")
CURRENCIES = ("copper", "silver", "gold", "magic_gold", "ancient_coin")

_store = EntityStore(
    env_var="TAVERN_CONSTRUCTOR_PATH",
    default_rel="data/tavern_constructor.json",
    statuses=STATUSES,  # noqa: F405
    transitions=TRANSITIONS,  # noqa: F405
    initial_status=STATUS_DRAFT,  # noqa: F405
)


def store() -> EntityStore:
    return _store


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _str(data: dict[str, Any], key: str) -> str:
    return str(data.get(key) or "").strip()


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not _str(data, "name"):
        errors.append("Не заполнено название таверны.")
    ttype = _str(data, "tavern_type")
    if ttype and ttype not in TAVERN_TYPES:
        errors.append(f"Неизвестный тип таверны: {ttype}.")
    mode = _str(data, "tavern_mode")
    if mode and mode not in TAVERN_MODES:
        errors.append(f"Неизвестный статус таверны: {mode}.")
    if not _str(data, "location_id") and not _str(data, "city_id"):
        warnings.append("Таверна не привязана к локации или городу (ТЗ §22).")
    if not _str(data, "player_entry_text"):
        warnings.append("Не задан текст входа в таверну (ТЗ §22).")

    def _check_price(row: dict[str, Any], label: str) -> None:
        price = _num(row.get("price"))
        if price is not None and price < 0:
            errors.append(f"{label}: цена не может быть отрицательной.")
        if price is not None and price > 0 and not str(row.get("currency") or "").strip():
            warnings.append(f"{label}: платная услуга без валюты.")

    for i, s in enumerate(data.get("services") or [], start=1):
        if isinstance(s, dict):
            st = str(s.get("service_type") or "").strip()
            if st and st not in SERVICE_TYPES:
                warnings.append(f"Услуга #{i}: тип «{st}» не из списка.")
            _check_price(s, f"Услуга #{i}")
    for i, m in enumerate(data.get("menu") or [], start=1):
        if isinstance(m, dict):
            cat = str(m.get("menu_category") or "").strip()
            if cat and cat not in MENU_CATEGORIES:
                warnings.append(f"Меню #{i}: категория «{cat}» не из списка.")
            _check_price(m, f"Меню #{i}")
            if not str(m.get("name") or m.get("linked_item_id") or "").strip():
                errors.append(f"Меню #{i}: нет названия и не указан предмет.")
    for i, r in enumerate(data.get("rumors") or [], start=1):
        if isinstance(r, dict) and not str(r.get("rumor_text") or "").strip():
            errors.append(f"Слух #{i}: пустой текст.")
    for i, rk in enumerate(data.get("risks") or [], start=1):
        if isinstance(rk, dict):
            rt = str(rk.get("risk_type") or "").strip()
            if rt and rt not in RISK_TYPES:
                warnings.append(f"Риск #{i}: тип «{rt}» не из списка.")
            if not str(rk.get("player_text") or "").strip():
                warnings.append(f"Риск #{i}: нет текста для игрока.")
    for i, ev in enumerate(data.get("events") or [], start=1):
        if isinstance(ev, dict):
            if (_num(ev.get("chance_percent")) or 0) <= 0 and (_num(ev.get("weight")) or 0) <= 0:
                warnings.append(f"Событие #{i}: не задан ни шанс, ни вес.")
    for i, sc in enumerate(data.get("schedule") or [], start=1):
        if isinstance(sc, dict):
            sm = str(sc.get("mode") or "").strip()
            if sm and sm not in SCHEDULE_MODES:
                warnings.append(f"Расписание #{i}: режим «{sm}» не из списка.")
            if sm and sm != "always" and not str(sc.get("fallback_text") or "").strip():
                warnings.append(f"Расписание #{i}: нет fallback-текста.")

    for key in ("name", "short_name", "description", "short_description",
                "player_entry_text", "admin_description"):
        value = _str(data, key)
        if value and (_HTML_RE.search(value) or "<script" in value.lower()):
            errors.append(f"В поле «{key}» недопустим HTML.")
    image = _str(data, "image_path")
    if image and (image.startswith("http://") or image.startswith("https://")):
        errors.append("Изображение должно быть локальным путём (/assets/…), не URL.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def final_price(base_price: Any, *, reputation_discount_percent: float = 0,
                event_modifier_percent: float = 0, min_price: int = 0) -> int:
    """Итоговая цена услуги таверны (ТЗ §10/§17). Игроку формула не видна."""
    base = _num(base_price) or 0
    price = base * (1 + event_modifier_percent / 100.0) * (1 - reputation_discount_percent / 100.0)
    return max(int(min_price), math.ceil(price))


def preview(data: dict[str, Any], mock: dict[str, Any] | None = None) -> dict[str, Any]:
    """Предпросмотр таверны для игрока (ТЗ §21): текст входа, доступные услуги/
    меню с итоговыми ценами, образец слуха, кнопки. mock: {has_money, reputation_
    discount_percent, ...}."""
    mock = mock or {}
    disc = _num(mock.get("reputation_discount_percent")) or 0
    ev_mod = _num(mock.get("event_modifier_percent")) or 0

    def _priced(rows: list[Any]) -> list[dict[str, Any]]:
        out = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("is_visible") or "true").lower() == "false":
                continue
            out.append({
                "name": row.get("name") or row.get("linked_item_id") or "—",
                "price": final_price(row.get("price"), reputation_discount_percent=disc,
                                     event_modifier_percent=ev_mod),
                "currency": row.get("currency") or "copper",
            })
        return out

    rumors = [r for r in (data.get("rumors") or []) if isinstance(r, dict) and str(r.get("rumor_text") or "").strip()]
    buttons = [str(b.get("text") or "") for b in (data.get("buttons") or []) if isinstance(b, dict) and str(b.get("text") or "").strip()]
    if not buttons:
        buttons = ["Меню", "Отдохнуть", "Спросить слухи", "Назад"]
    return {
        "entry_text": data.get("player_entry_text") or data.get("description") or data.get("name") or "Таверна",
        "services": _priced(data.get("services") or []),
        "menu": _priced(data.get("menu") or []),
        "rest_options": _priced(data.get("rest_options") or []),
        "rumor": (rumors[0].get("rumor_text") if rumors else "Сегодня никто не рассказал вам ничего полезного."),
        "buttons": buttons,
    }
