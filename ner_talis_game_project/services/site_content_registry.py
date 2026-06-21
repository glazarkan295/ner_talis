"""Конструктор сайта V2 (ТЗ «Конструктор сайта…») — публикуемый контент.

Генерик-реестр публикуемого контента сайта (новости/гайды/FAQ/баннеры/
объявления) с жизненным циклом draft→review→ready→scheduled→published→hidden→
archived и валидацией (§28: заголовок/текст, нет HTML/скриптов, корректные
даты). По духу повторяет world_content_registry, но со своими kind/валидаторами.

Аудит и права — в роутере (admin_site_api). Рейтинги, торговые павильоны и
раскладка профиля — отдельные подсистемы на вырост.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable

from services.admin_entity_store import EntityStore

# --- Статусы (ТЗ §13, §28) --------------------------------------------------
STATUS_DRAFT = "draft"
STATUS_REVIEW = "review"
STATUS_READY = "ready"
STATUS_SCHEDULED = "scheduled"
STATUS_PUBLISHED = "published"
STATUS_HIDDEN = "hidden"
STATUS_ARCHIVE = "archive"
STATUS_ERROR = "error"

STATUSES = (
    STATUS_DRAFT, STATUS_REVIEW, STATUS_READY, STATUS_SCHEDULED,
    STATUS_PUBLISHED, STATUS_HIDDEN, STATUS_ARCHIVE, STATUS_ERROR,
)
STATUS_LABELS = {
    STATUS_DRAFT: "Черновик", STATUS_REVIEW: "На проверке", STATUS_READY: "Готово к публикации",
    STATUS_SCHEDULED: "Запланировано", STATUS_PUBLISHED: "Опубликовано", STATUS_HIDDEN: "Скрыто",
    STATUS_ARCHIVE: "Архив", STATUS_ERROR: "Ошибка проверки",
}
TRANSITIONS: dict[str, set[str]] = {
    STATUS_DRAFT: {STATUS_REVIEW, STATUS_READY, STATUS_SCHEDULED, STATUS_ARCHIVE, STATUS_ERROR},
    STATUS_REVIEW: {STATUS_DRAFT, STATUS_READY, STATUS_ARCHIVE, STATUS_ERROR},
    STATUS_READY: {STATUS_DRAFT, STATUS_SCHEDULED, STATUS_PUBLISHED, STATUS_ARCHIVE, STATUS_ERROR},
    STATUS_SCHEDULED: {STATUS_PUBLISHED, STATUS_DRAFT, STATUS_HIDDEN, STATUS_ARCHIVE},
    STATUS_PUBLISHED: {STATUS_HIDDEN, STATUS_ARCHIVE},
    STATUS_HIDDEN: {STATUS_PUBLISHED, STATUS_DRAFT, STATUS_ARCHIVE},
    STATUS_ARCHIVE: {STATUS_DRAFT},
    STATUS_ERROR: {STATUS_DRAFT, STATUS_REVIEW, STATUS_ARCHIVE},
}

# --- Типы контента + справочники --------------------------------------------
KIND_NEWS = "news"
KIND_GUIDE = "guide"
KIND_FAQ = "faq"
KIND_BANNER = "banner"
KIND_ANNOUNCEMENT = "announcement"
KINDS = (KIND_NEWS, KIND_GUIDE, KIND_FAQ, KIND_BANNER, KIND_ANNOUNCEMENT)

NEWS_CATEGORIES = (
    "Обновления", "Технические работы", "События", "Праздники", "Баланс",
    "Новые локации", "Новые мобы", "Гильдии", "Рейды", "Промокоды", "Важное", "Лор",
)
GUIDE_DIFFICULTIES = ("novice", "normal", "advanced", "admin", "service")
BANNER_TYPES = (
    "info", "warning", "maintenance", "event", "festive", "promo", "danger", "update",
)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{1,63}$")
_HTML_TAG_RE = re.compile(r"<[^>]+>")

_store = EntityStore(
    env_var="SITE_CONTENT_PATH",
    default_rel="data/site_content.json",
    statuses=STATUSES,
    transitions=TRANSITIONS,
    initial_status=STATUS_DRAFT,
)


def store() -> EntityStore:
    return _store


def _str(data: dict[str, Any], key: str) -> str:
    return str(data.get(key) or "").strip()


def _has_markup(value: str) -> bool:
    """Запрет HTML/скриптов в материалах сайта (ТЗ §28)."""
    low = value.lower()
    return "<script" in low or "javascript:" in low or bool(_HTML_TAG_RE.search(value))


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _validate_common(data: dict[str, Any], *, title_key: str, body_key: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not _str(data, title_key):
        errors.append("Заголовок не заполнен.")
    if not _str(data, body_key):
        errors.append("Текст не заполнен.")
    # Нет запрещённых HTML/скриптов (ТЗ §28).
    for key in (title_key, body_key, "short_description"):
        value = _str(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимый HTML/скрипт.")
    start = _parse_date(data.get("publish_at") or data.get("start_date"))
    end = _parse_date(data.get("end_at") or data.get("end_date"))
    if (data.get("publish_at") or data.get("start_date")) and start is None:
        errors.append("Некорректная дата публикации.")
    if start and end and end <= start:
        errors.append("Дата окончания показа должна быть позже даты публикации.")
    return errors, warnings


def _validate_news(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    errors, warnings = _validate_common(data, title_key="title", body_key="body")
    category = _str(data, "category")
    if category and category not in NEWS_CATEGORIES:
        warnings.append(f"Категория «{category}» не из стандартного списка.")
    return errors, warnings


def _validate_guide(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    errors, warnings = _validate_common(data, title_key="title", body_key="body")
    diff = _str(data, "difficulty")
    if diff and diff not in GUIDE_DIFFICULTIES:
        errors.append(f"Неизвестная сложность гайда: {diff}.")
    return errors, warnings


def _validate_faq(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    return _validate_common(data, title_key="question", body_key="answer")


def _validate_banner(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    errors, warnings = _validate_common(data, title_key="title", body_key="text")
    btype = _str(data, "type")
    if btype and btype not in BANNER_TYPES:
        errors.append(f"Неизвестный тип баннера: {btype}.")
    return errors, warnings


VALIDATORS: dict[str, Callable[[dict[str, Any]], tuple[list[str], list[str]]]] = {
    KIND_NEWS: _validate_news,
    KIND_GUIDE: _validate_guide,
    KIND_FAQ: _validate_faq,
    KIND_BANNER: _validate_banner,
    KIND_ANNOUNCEMENT: _validate_banner,  # объявление — как баннер
}


def validate(kind: str, envelope: dict[str, Any]) -> dict[str, Any]:
    validator = VALIDATORS.get(kind)
    if validator is None:
        return {"ok": False, "errors": [f"Неизвестный тип контента: {kind}."], "warnings": []}
    errors, warnings = validator(envelope)
    return {"ok": not errors, "errors": errors, "warnings": warnings}
