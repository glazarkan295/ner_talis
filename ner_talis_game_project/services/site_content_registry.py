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
# Расширение конструктора сайта (ТЗ §2): публичные страницы и их структура.
KIND_PAGE = "page"            # §2.3 публичная страница
KIND_PAGE_BLOCK = "page_block"  # §2.4 блок страницы
KIND_MENU_ITEM = "menu_item"  # §2.5 пункт меню навигации
KIND_POST = "post"            # §2.6 пост/новость (расширенная)
KIND_RATING = "rating"        # §2.7 рейтинг
KIND_LORE = "lore"            # §2.10 запись лора
KIND_WHERE_IS = "where_is"    # §2.11 «Что где находится»
KIND_THEME = "site_theme"     # §2.12 фон/оформление/цвета сайта
KINDS = (
    KIND_NEWS, KIND_GUIDE, KIND_FAQ, KIND_BANNER, KIND_ANNOUNCEMENT,
    KIND_PAGE, KIND_PAGE_BLOCK, KIND_MENU_ITEM, KIND_POST, KIND_RATING,
    KIND_LORE, KIND_WHERE_IS, KIND_THEME,
)

NEWS_CATEGORIES = (
    "Обновления", "Технические работы", "События", "Праздники", "Баланс",
    "Новые локации", "Новые мобы", "Гильдии", "Рейды", "Промокоды", "Важное", "Лор",
)
GUIDE_DIFFICULTIES = ("novice", "normal", "advanced", "admin", "service")
BANNER_TYPES = (
    "info", "warning", "maintenance", "event", "festive", "promo", "danger", "update",
)

# --- Справочники расширенного конструктора сайта (ТЗ §2) ---------------------
PAGE_BLOCK_TYPES = (  # §2.4
    "heading", "text", "image", "gallery", "banner", "card", "list", "table",
    "button", "link", "quote", "warning", "news", "guide", "faq", "lore",
    "rating", "where_is", "items", "mobs", "locations", "city", "fortress",
)
PAGE_VISIBILITIES = ("public", "authorized", "hidden")  # §2.3 видимость
BLOCK_WIDTHS = ("full", "half", "third", "quarter")     # §2.4 ширина
BLOCK_ALIGNS = ("left", "center", "right")              # §2.4 выравнивание
RATING_TYPES = (  # §2.7
    "level", "exp", "wins", "pvp", "loot", "craft", "events", "raids",
    "wealth", "weekly", "monthly", "seasonal",
)
RATING_PERIODS = ("all_time", "weekly", "monthly", "seasonal")  # §2.7 период
LORE_TYPES = (  # §2.10
    "history", "ancient_record", "diary", "book", "note", "legend", "race",
    "city", "ancient_place", "seldar", "fortress", "ner_vir", "ancients",
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


def _validate_required(data: dict[str, Any], key: str, label: str) -> list[str]:
    return [] if _str(data, key) else [f"{label} не заполнено."]


def _no_markup_errors(data: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    errors: list[str] = []
    for key in keys:
        value = _str(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимый HTML/скрипт.")
    return errors


def _validate_page(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    errors = _validate_required(data, "title", "Название страницы")
    errors += _no_markup_errors(data, ("title", "body", "short_description", "seo_title", "seo_description"))
    visibility = _str(data, "visibility")
    if visibility and visibility not in PAGE_VISIBILITIES:
        errors.append(f"Неизвестная видимость страницы: {visibility}.")
    warnings: list[str] = []
    if not _str(data, "slug"):
        warnings.append("Не задан адрес страницы (slug) — будет использован ID.")
    return errors, warnings


def _validate_page_block(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    errors = _validate_required(data, "title", "Название блока")
    block_type = _str(data, "block_type")
    if not block_type:
        errors.append("Не выбран тип блока.")
    elif block_type not in PAGE_BLOCK_TYPES:
        errors.append(f"Неизвестный тип блока: {block_type}.")
    width = _str(data, "width")
    if width and width not in BLOCK_WIDTHS:
        errors.append(f"Неизвестная ширина блока: {width}.")
    align = _str(data, "align")
    if align and align not in BLOCK_ALIGNS:
        errors.append(f"Неизвестное выравнивание: {align}.")
    errors += _no_markup_errors(data, ("title", "content"))
    return errors, []


def _validate_menu_item(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    errors = _validate_required(data, "label", "Подпись пункта меню")
    errors += _no_markup_errors(data, ("label",))
    warnings: list[str] = []
    if not _str(data, "link") and not _str(data, "page_id"):
        warnings.append("У пункта меню не задана ссылка и не выбрана страница.")
    return errors, warnings


def _validate_post(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    errors, warnings = _validate_common(data, title_key="title", body_key="body")
    category = _str(data, "category")
    if category and category not in NEWS_CATEGORIES:
        warnings.append(f"Категория «{category}» не из стандартного списка.")
    return errors, warnings


def _validate_rating(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    errors = _validate_required(data, "title", "Название рейтинга")
    rating_type = _str(data, "rating_type")
    if rating_type and rating_type not in RATING_TYPES:
        errors.append(f"Неизвестный тип рейтинга: {rating_type}.")
    period = _str(data, "period")
    if period and period not in RATING_PERIODS:
        errors.append(f"Неизвестный период рейтинга: {period}.")
    errors += _no_markup_errors(data, ("title", "description"))
    return errors, []


def _validate_lore(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    errors, warnings = _validate_common(data, title_key="title", body_key="text")
    lore_type = _str(data, "lore_type")
    if lore_type and lore_type not in LORE_TYPES:
        errors.append(f"Неизвестный тип записи лора: {lore_type}.")
    return errors, warnings


def _validate_where_is(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    errors = _validate_required(data, "title", "Название записи")
    errors += _no_markup_errors(data, ("title", "short_answer", "description"))
    warnings: list[str] = []
    if not _str(data, "place"):
        warnings.append("Не указано, где находится (город/крепость/локация).")
    return errors, warnings


def _validate_theme(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    errors = _validate_required(data, "title", "Название оформления")
    warnings: list[str] = []
    opacity = data.get("block_opacity")
    if opacity not in (None, ""):
        try:
            value = float(opacity)
            if value < 0 or value > 100:
                errors.append("Прозрачность блоков должна быть 0–100.")
        except (TypeError, ValueError):
            errors.append("Прозрачность блоков — не число.")
    return errors, warnings


VALIDATORS: dict[str, Callable[[dict[str, Any]], tuple[list[str], list[str]]]] = {
    KIND_NEWS: _validate_news,
    KIND_GUIDE: _validate_guide,
    KIND_FAQ: _validate_faq,
    KIND_BANNER: _validate_banner,
    KIND_ANNOUNCEMENT: _validate_banner,  # объявление — как баннер
    KIND_PAGE: _validate_page,
    KIND_PAGE_BLOCK: _validate_page_block,
    KIND_MENU_ITEM: _validate_menu_item,
    KIND_POST: _validate_post,
    KIND_RATING: _validate_rating,
    KIND_LORE: _validate_lore,
    KIND_WHERE_IS: _validate_where_is,
    KIND_THEME: _validate_theme,
}


def validate(kind: str, envelope: dict[str, Any]) -> dict[str, Any]:
    validator = VALIDATORS.get(kind)
    if validator is None:
        return {"ok": False, "errors": [f"Неизвестный тип контента: {kind}."], "warnings": []}
    errors, warnings = validator(envelope)
    return {"ok": not errors, "errors": errors, "warnings": warnings}


# --- Публичное чтение опубликованного контента (рантайм сайта, ТЗ §2) -------
def _public_view(env: dict[str, Any]) -> dict[str, Any]:
    """Безопасное публичное представление записи: только данные контента."""
    data = dict(env.get("data") or {})
    data.pop("_kind", None)
    return {"id": env.get("id"), "updated_at": env.get("updated_at"), **data}


def _order(env: dict[str, Any]) -> tuple[float, str]:
    data = env.get("data") or {}
    raw = data.get("menu_order", data.get("order"))
    try:
        num = float(raw)
    except (TypeError, ValueError):
        num = 0.0
    return (num, str(data.get("title") or data.get("label") or env.get("id") or ""))


def _is_public(env: dict[str, Any]) -> bool:
    """Запись доступна анонимному посетителю? (Codex P2: hidden/authorized —
    не отдавать публично, даже если статус published.)"""
    visibility = str((env.get("data") or {}).get("visibility") or "").strip().lower()
    return visibility not in ("hidden", "authorized")


def published(kind: str) -> list[dict[str, Any]]:
    """Опубликованные записи указанного типа (для публичного сайта), по порядку.
    Непубличные по видимости (hidden/authorized) не отдаются."""
    items = [
        i for i in _store.list(status=STATUS_PUBLISHED)
        if (i.get("data") or {}).get("_kind") == kind and _is_public(i)
    ]
    items.sort(key=_order)
    return [_public_view(i) for i in items]


def published_menu() -> list[dict[str, Any]]:
    """Меню навигации деревом по parent_id (только опубликованные пункты)."""
    flat = published(KIND_MENU_ITEM)
    by_id = {item["id"]: {**item, "children": []} for item in flat}
    roots: list[dict[str, Any]] = []
    for item in flat:
        parent = str(item.get("parent_id") or "")
        if parent and parent in by_id:
            by_id[parent]["children"].append(by_id[item["id"]])
        else:
            roots.append(by_id[item["id"]])
    return roots


def published_page(slug_or_id: str) -> dict[str, Any] | None:
    """Опубликованная страница по адресу (slug) или id + её опубликованные блоки."""
    key = str(slug_or_id or "").strip()
    if not key:
        return None
    page_env = None
    for env in _store.list(status=STATUS_PUBLISHED):
        data = env.get("data") or {}
        if data.get("_kind") != KIND_PAGE:
            continue
        if env.get("id") == key or str(data.get("slug") or "") == key:
            page_env = env
            break
    if page_env is None or not _is_public(page_env):
        return None
    page = _public_view(page_env)
    blocks = [
        b for b in published(KIND_PAGE_BLOCK)
        if str(b.get("page_id") or "") == page["id"]
    ]
    page["blocks"] = blocks
    return page


def where_used(object_id: str) -> list[dict[str, Any]]:
    """Где используется материал сайта (ТЗ §6): блоки страницы/пункты меню,
    ссылающиеся на страницу, и дочерние пункты меню."""
    oid = str(object_id or "").strip()
    if not oid:
        return []
    refs: list[dict[str, Any]] = []
    for env in _store.list():
        data = env.get("data") or {}
        kind = str(data.get("_kind") or "")
        fields: list[str] = []
        if kind == KIND_PAGE_BLOCK and str(data.get("page_id") or "") == oid:
            fields.append("блок страницы")
        if kind == KIND_MENU_ITEM:
            if str(data.get("page_id") or "") == oid:
                fields.append("пункт меню ведёт на страницу")
            if str(data.get("parent_id") or "") == oid:
                fields.append("дочерний пункт меню")
        if fields:
            name = data.get("title") or data.get("label") or data.get("question") or env.get("id")
            refs.append({"id": env.get("id"), "kind": kind, "name": str(name), "fields": fields})
    return refs
