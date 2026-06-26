"""Конструктор сообщений мастерских (ТЗ 14).

Запись = шаблон отображения сообщения мастерской: порядок блоков, группировка/
сортировка списков рецептов, показ материалов/требований/очереди, кнопки,
формат отправки и пагинация. Хранение — EntityStore
(data/workshop_message_constructor.json). Включает рендер-предпросмотр (§12) и
проверку шаблона (§15) без обращения к рантайму.
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")
_PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")
MAX_BUTTONS = 12
MAX_MESSAGE_LENGTH = 3500  # запас под лимит Telegram (4096)

# Блоки сообщения (§4) в порядке по умолчанию.
BLOCK_TYPES = (
    "header", "description", "available_recipes", "unavailable_recipes",
    "materials", "requirements", "queue", "completed", "hints", "buttons",
)
BLOCK_LABELS = {
    "header": "Заголовок", "description": "Описание", "available_recipes": "Доступные рецепты",
    "unavailable_recipes": "Недоступные рецепты", "materials": "Материалы",
    "requirements": "Требования", "queue": "Очередь создания", "completed": "Завершённые работы",
    "hints": "Подсказки", "buttons": "Кнопки",
}
SCOPES = ("global", "by_type", "by_workshop")
SCOPE_LABELS = {"global": "Общий шаблон", "by_type": "По типу мастерской", "by_workshop": "Для мастерской"}
GROUPING_MODES = (
    "none", "by_item_type", "by_profession", "by_workshop", "by_level",
    "by_availability", "by_quality", "by_rarity", "favorites", "recent", "manual",
)
SORT_MODES = (
    "alpha", "level", "availability", "available_first", "favorites_first",
    "new_first", "frequent_first", "time", "cost", "quality", "rarity", "manual",
)
UNAVAILABLE_DISPLAY = ("hide", "gray", "name_only", "name_reason", "after_level", "if_blueprint", "if_seen")
SEND_FORMATS = ("single", "multiple")
# Допустимые плейсхолдеры в текстах результата/заголовка (§15).
KNOWN_PLACEHOLDERS = frozenset({
    "item", "count", "quality", "workshop", "profession", "level", "exp",
    "time", "cost", "player", "result", "amount",
})

_store = EntityStore(
    env_var="WORKSHOP_MESSAGE_CONSTRUCTOR_PATH",
    default_rel="data/workshop_message_constructor.json",
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


def _unknown_placeholders(text: str) -> list[str]:
    return [m for m in _PLACEHOLDER_RE.findall(str(text or "")) if m not in KNOWN_PLACEHOLDERS]


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not str(data.get("name") or "").strip():
        errors.append("Не заполнено название шаблона.")
    scope = str(data.get("scope") or "").strip()
    if scope and scope not in SCOPES:
        errors.append(f"Неизвестная область шаблона: {scope}.")
    if scope == "by_workshop" and not str(data.get("workshop_id") or "").strip():
        warnings.append("Шаблон привязан к мастерской, но мастерская не указана.")

    order = data.get("block_order")
    if order not in (None, ""):
        if not isinstance(order, list):
            errors.append("Порядок блоков должен быть списком.")
        else:
            seen: set[str] = set()
            for b in order:
                if b not in BLOCK_TYPES:
                    errors.append(f"Неизвестный блок в порядке: {b}.")
                elif b in seen:
                    warnings.append(f"Блок «{BLOCK_LABELS.get(b, b)}» указан дважды.")
                seen.add(b)

    grouping = str(data.get("grouping") or "").strip()
    if grouping and grouping not in GROUPING_MODES:
        errors.append(f"Неизвестная группировка: {grouping}.")
    sorting = str(data.get("sorting") or "").strip()
    if sorting and sorting not in SORT_MODES:
        errors.append(f"Неизвестная сортировка: {sorting}.")
    unavailable = str(data.get("unavailable_display") or "").strip()
    if unavailable and unavailable not in UNAVAILABLE_DISPLAY:
        errors.append(f"Неизвестный режим показа недоступных: {unavailable}.")
    send_format = str(data.get("send_format") or "").strip()
    if send_format and send_format not in SEND_FORMATS:
        errors.append(f"Неизвестный формат отправки: {send_format}.")

    if data.get("use_pagination"):
        per_page = _num(data.get("items_per_page"))
        if per_page is None or per_page < 1:
            errors.append("Количество элементов на странице должно быть ≥ 1.")

    buttons = data.get("buttons")
    if isinstance(buttons, list) and len(buttons) > MAX_BUTTONS:
        warnings.append(f"Слишком много кнопок ({len(buttons)} > {MAX_BUTTONS}) — сообщение перегружено (§15).")

    # Плейсхолдеры (§15).
    result_texts = data.get("result_texts") if isinstance(data.get("result_texts"), dict) else {}
    for key in ("header", "description"):
        for ph in _unknown_placeholders(data.get(key)):
            warnings.append(f"В поле «{key}» неизвестная переменная {{{ph}}}.")
    for key, value in result_texts.items():
        for ph in _unknown_placeholders(value):
            warnings.append(f"В тексте результата «{key}» неизвестная переменная {{{ph}}}.")

    # Безопасность текстов.
    for key in ("name", "header", "description"):
        value = str(data.get(key) or "").strip()
        if value and (_HTML_RE.search(value) or "<script" in value.lower()):
            errors.append(f"В поле «{key}» недопустим HTML.")

    # Оценка длины предпросмотра (§15).
    preview = render_preview(data, None)
    if preview.get("length", 0) > MAX_MESSAGE_LENGTH and send_format != "multiple":
        warnings.append(f"Сообщение длинное ({preview['length']} симв.) — включите пагинацию или несколько сообщений.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


# --- Предпросмотр (ТЗ §12) -------------------------------------------------
_SAMPLE_STATE = {
    "workshop_name": "Кузница",
    "recipes": [
        {"name": "Железный меч", "available": True},
        {"name": "Железный кинжал", "available": False, "reason": "не хватает материалов"},
    ],
    "materials": [
        {"name": "Железная руда", "need": 5, "have": 5},
        {"name": "Уголь", "need": 3, "have": 1},
    ],
    "requirements": [{"text": "Уровень профессии 5", "met": True}],
    "queue": [{"name": "Железный слиток", "remaining": "00:45"}],
}


def render_preview(data: dict[str, Any], state: dict[str, Any] | None) -> dict[str, Any]:
    """Собрать текстовый предпросмотр сообщения мастерской по шаблону и состоянию."""
    state = state or _SAMPLE_STATE
    order = data.get("block_order") if isinstance(data.get("block_order"), list) else list(BLOCK_TYPES)
    per_page = int(_num(data.get("items_per_page")) or 0) if data.get("use_pagination") else 0
    unavailable = str(data.get("unavailable_display") or "name_reason")
    lines: list[str] = []
    blocks: list[dict[str, Any]] = []

    def _emit(title: str, body: list[str]) -> None:
        blocks.append({"title": title, "lines": body})
        lines.extend(body)

    for block in order:
        if block == "header":
            txt = str(data.get("header") or state.get("workshop_name") or "Мастерская")
            _emit("header", [f"⚒ {txt}"])
        elif block == "description":
            if str(data.get("description") or "").strip():
                _emit("description", [str(data["description"])])
        elif block == "available_recipes":
            recs = [r for r in state.get("recipes", []) if r.get("available")]
            if per_page:
                recs = recs[:per_page]
            body = ["Доступные рецепты:"] + [f"• {r['name']}" for r in recs]
            _emit("available_recipes", body)
        elif block == "unavailable_recipes":
            if unavailable == "hide":
                continue
            recs = [r for r in state.get("recipes", []) if not r.get("available")]
            if per_page:
                recs = recs[:per_page]
            body = ["Недоступные рецепты:"]
            for r in recs:
                if unavailable == "name_only":
                    body.append(f"• {r['name']}")
                else:
                    body.append(f"• {r['name']} — {r.get('reason', 'недоступно')}")
            _emit("unavailable_recipes", body)
        elif block == "materials":
            body = ["Материалы:"]
            for m in state.get("materials", []):
                ok = (m.get("have", 0) >= m.get("need", 0))
                if data.get("show_only_missing") and ok:
                    continue
                body.append(f"{'✅' if ok else '❌'} {m['name']}: {m.get('have', 0)}/{m.get('need', 0)}")
            _emit("materials", body)
        elif block == "requirements":
            body = ["Требования:"]
            for rq in state.get("requirements", []):
                if data.get("requirements_display") == "unmet_only" and rq.get("met"):
                    continue
                body.append(f"{'✅' if rq.get('met') else '❌'} {rq['text']}")
            _emit("requirements", body)
        elif block == "queue":
            mode = str(data.get("show_queue") or "if_active")
            q = state.get("queue", [])
            if mode == "never" or (mode == "if_active" and not q):
                continue
            body = ["Очередь:"] + [f"⏳ {x['name']} — осталось {x.get('remaining', '?')}" for x in q]
            _emit("queue", body)
        elif block == "hints":
            hints = data.get("hints") if isinstance(data.get("hints"), list) else []
            if hints:
                _emit("hints", [f"💡 {h}" for h in hints])
        elif block == "buttons":
            btns = data.get("buttons") if isinstance(data.get("buttons"), list) else []
            labels = [str(b.get("text") or "") for b in btns if str(b.get("text") or "").strip()]
            if labels:
                _emit("buttons", ["[ " + " ] [ ".join(labels) + " ]"])

    text = "\n".join(lines)
    return {"text": text, "blocks": blocks, "length": len(text)}
