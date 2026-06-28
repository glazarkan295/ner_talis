"""Конструктор текстов бота (full-import ТЗ §5.18): редактируемые сообщения.

Запись = один текст: ключ поиска (text_key), значение (text_value), контекст,
привязка к сущности (entity_type/entity_id), платформа, режим разметки,
переменные-плейсхолдеры, fallback. Хранение — EntityStore
(data/text_constructor.json). Чистый слой данных + валидация + подстановка
плейсхолдеров; рантайм-чтение игрой — text_runtime под feature flag
use_v2_texts (по умолчанию ВЫКЛ, fallback на старый код).
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")
_KEY_RE = re.compile(r"^[a-zA-Z0-9_.:-]{2,120}$")

PLATFORMS = ("both", "telegram", "vk")
PLATFORM_LABELS = {"both": "Обе платформы", "telegram": "Telegram", "vk": "VK"}
PARSE_MODES = ("none", "HTML", "Markdown", "MarkdownV2")
# Контексты/категории текстов (§5.18).
CONTEXTS = (
    "location", "button", "event", "search", "battle", "craft", "error",
    "fine", "delivery", "promo", "reward", "npc", "quest", "transition",
    "camp", "death", "curse", "achievement", "system", "other",
)
CONTEXT_LABELS = {
    "location": "Локации", "button": "Кнопки", "event": "События",
    "search": "Поиск", "battle": "Бой", "craft": "Ремесло", "error": "Ошибки",
    "fine": "Штрафы", "delivery": "Доставка", "promo": "Промокоды",
    "reward": "Награды", "npc": "NPC", "quest": "Задания",
    "transition": "Переходы", "camp": "Лагерь", "death": "Смерть",
    "curse": "Проклятия", "achievement": "Достижения",
    "system": "Системные", "other": "Прочее",
}
ENTITY_TYPES = (
    "none", "location", "button", "event", "item", "mob", "npc", "quest",
    "fine", "promo", "achievement", "effect", "reputation", "skill", "other",
)
# Лимиты Telegram (для предупреждений).
TELEGRAM_TEXT_LIMIT = 4096

_store = EntityStore(
    env_var="TEXT_CONSTRUCTOR_PATH",
    default_rel="data/text_constructor.json",
    statuses=STATUSES,  # noqa: F405
    transitions=TRANSITIONS,  # noqa: F405
    initial_status=STATUS_DRAFT,  # noqa: F405
)


def store() -> EntityStore:
    return _store


def placeholders_in(text: Any) -> list[str]:
    """Список плейсхолдеров {name}, встречающихся в тексте (без повторов)."""
    return sorted(set(_PLACEHOLDER_RE.findall(str(text or ""))))


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    key = str(data.get("text_key") or "").strip()
    if not key:
        errors.append("Не заполнен ключ текста (text_key).")
    elif not _KEY_RE.match(key):
        warnings.append("Ключ текста: рекомендуется латиница/цифры/._:- (2–120 символов).")

    value = str(data.get("text_value") or "").strip()
    fallback = str(data.get("fallback_text") or "").strip()
    if not value and not fallback:
        errors.append("Текст пустой и нет fallback_text.")

    platform = str(data.get("platform") or "both").strip()
    if platform not in PLATFORMS:
        errors.append(f"Неизвестная платформа: {platform}.")

    parse_mode = str(data.get("parse_mode") or "none").strip()
    if parse_mode not in PARSE_MODES:
        errors.append(f"Неизвестный режим разметки: {parse_mode}.")

    context = str(data.get("context") or "").strip()
    if context and context not in CONTEXTS:
        warnings.append(f"Контекст «{context}» не из стандартного списка.")

    etype = str(data.get("entity_type") or "").strip()
    if etype and etype not in ENTITY_TYPES:
        warnings.append(f"Тип сущности «{etype}» не из списка.")

    # HTML только при parse_mode=HTML, иначе теги покажутся как есть.
    if value and parse_mode != "HTML" and _HTML_RE.search(value):
        warnings.append("В тексте есть HTML-теги, но режим разметки не HTML — теги покажутся как текст.")

    # Согласованность переменных: объявленные variables vs реально использованные.
    declared = [str(v).strip() for v in (data.get("variables") or []) if str(v).strip()]
    used = placeholders_in(value or fallback)
    for v in used:
        if v not in declared:
            warnings.append(f"Плейсхолдер {{{v}}} не объявлен в variables.")
    for v in declared:
        if v not in used:
            warnings.append(f"Переменная «{v}» объявлена, но не используется в тексте.")

    if len(value) > TELEGRAM_TEXT_LIMIT:
        warnings.append(f"Текст длиннее {TELEGRAM_TEXT_LIMIT} символов — Telegram не отправит одним сообщением.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def render(data: dict[str, Any], variables: dict[str, Any] | None = None) -> str:
    """Подставить переменные в text_value (или fallback). Неизвестные {name} остаются."""
    text = str((data or {}).get("text_value") or "").strip()
    if not text:
        text = str((data or {}).get("fallback_text") or "")
    values = variables or {}

    def _repl(match: "re.Match[str]") -> str:
        name = match.group(1)
        return str(values[name]) if name in values else match.group(0)

    return _PLACEHOLDER_RE.sub(_repl, text)
