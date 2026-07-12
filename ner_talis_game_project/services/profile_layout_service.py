"""Конструктор раскладки профиля игрока V2 (ТЗ §3).

Настраивает шаблон и права (profile_settings), ЧТО и в каком порядке игрок видит:
вкладки (profile_tab), блоки внутри вкладок (profile_block) и оформление (profile_theme).
Это слой данных + валидация; применение раскладки к профилю (site_api
frontend_profile) — отдельный рантайм-этап. Хранение — генерик EntityStore
(data/profile_layout.json) с тегом _kind. Аудит и права (profile_layout.*) —
в роутере admin_profile_layout_api.

Вкладка «Обзор» намеренно не входит в пресеты (ТЗ §3.3): её данные распределяются
по другим вкладкам. Читаемость опасных действий (§3.8) обеспечивается стилями
профиля (PlayerProfile.css .nt-danger), а не этим слоем.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from services.admin_entity_store import EntityStore

# --- Статусы (как у остальных конструкторов) --------------------------------
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

# --- Типы объектов раскладки ------------------------------------------------
KIND_TAB = "profile_tab"
KIND_BLOCK = "profile_block"
KIND_THEME = "profile_theme"
KIND_SETTINGS = "profile_settings"
KINDS = (KIND_SETTINGS, KIND_TAB, KIND_BLOCK, KIND_THEME)

# Пресеты вкладок (§3.3) — без «Обзора». Можно создавать и свои id.
TAB_PRESETS = (
    "character", "inventory", "skills", "services", "info", "effects",
    "activity", "pavilion", "achievements", "raids",
)
# Типы блоков профиля (§3.4).
PROFILE_BLOCK_TYPES = (
    "main_info", "resources", "stats", "equipment", "inventory", "effects",
    "fines", "warnings", "activity", "currency", "skills", "passive_skills",
    "services", "transfer", "pavilion", "danger_zone",
    "reputation", "ratings", "crafting", "achievements", "guild",
    "events",
)
VISIBILITIES = ("always", "has_data", "conditional", "hidden")  # §3.4 условия видимости
BLOCK_WIDTHS = ("full", "half", "third")  # §3.4 ширина

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{1,63}$")
_HTML_RE = re.compile(r"<[^>]+>")

_store = EntityStore(
    env_var="PROFILE_LAYOUT_PATH",
    default_rel="data/profile_layout.json",
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


def _validate_tab(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []
    if not _str(data, "label"):
        errors.append("Не заполнено название вкладки.")
    if _str(data, "label") and _has_markup(_str(data, "label")):
        errors.append("В названии вкладки недопустим HTML.")
    visibility = _str(data, "visibility")
    if visibility and visibility not in VISIBILITIES:
        errors.append(f"Неизвестная видимость вкладки: {visibility}.")
    order = data.get("order")
    if order not in (None, "") and _num(order) is None:
        errors.append("Порядок вкладки — не число.")
    # «Обзор» как вкладка не используется (§3.3).
    if _str(data, "tab_key").lower() in {"overview", "обзор"} or _str(data, "label").lower() == "обзор":
        errors.append("Вкладка «Обзор» запрещена — распределите данные по другим вкладкам.")
    return errors, warnings


def _validate_block(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []
    if not _str(data, "name"):
        errors.append("Не заполнено название блока.")
    block_type = _str(data, "block_type")
    if not block_type:
        errors.append("Не выбран тип блока.")
    elif block_type not in PROFILE_BLOCK_TYPES:
        errors.append(f"Неизвестный тип блока: {block_type}.")
    if not _str(data, "tab"):
        warnings.append("Блок не привязан к вкладке (tab).")
    visibility = _str(data, "visibility")
    if visibility and visibility not in VISIBILITIES:
        errors.append(f"Неизвестная видимость блока: {visibility}.")
    width = _str(data, "width")
    if width and width not in BLOCK_WIDTHS:
        errors.append(f"Неизвестная ширина блока: {width}.")
    order = data.get("order")
    if order not in (None, "") and _num(order) is None:
        errors.append("Порядок блока — не число.")
    for key in ("name", "hint"):
        value = _str(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустим HTML.")
    return errors, warnings


def _validate_theme(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    if not _str(data, "title"):
        errors.append("Не заполнено название оформления.")
    for key,label in (("border_radius","Скругление"),("icon_size","Размер иконок"),("item_image_size","Размер изображений предметов")):
        if data.get(key) not in (None,"") and (_num(data.get(key)) is None or float(data.get(key))<0):errors.append(f"{label}: неотрицательное число.")
    if any(data.get(key) for key in ("character_model","race_model","gender_model","body_avatar")):errors.append("Визуальная модель персонажа в профиле запрещена.")
    return errors, []


def _validate_settings(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []
    if not _str(data, "title"):
        errors.append("Не заполнено название шаблона профиля.")
    if not _str(data, "system_name"):
        errors.append("Не заполнено системное название шаблона.")
    profile_type = _str(data, "profile_type")
    if profile_type and profile_type not in {"main", "mobile", "telegram", "vk", "site", "admin", "read_only", "test", "preview", "service"}:
        errors.append(f"Неизвестный тип профиля: {profile_type}.")
    if not any(bool(data.get(k)) for k in ("use_for_players", "use_for_admin", "use_for_test")):
        warnings.append("Шаблон не назначен ни одному режиму просмотра.")
    for key in ("title", "system_name", "description", "readonly_text"):
        if _has_markup(_str(data, key)):
            errors.append(f"В поле «{key}» недопустим HTML.")
    return errors, warnings


VALIDATORS: dict[str, Callable[[dict[str, Any]], tuple[list[str], list[str]]]] = {
    KIND_TAB: _validate_tab,
    KIND_BLOCK: _validate_block,
    KIND_THEME: _validate_theme,
    KIND_SETTINGS: _validate_settings,
}


def validate(kind: str, envelope: dict[str, Any]) -> dict[str, Any]:
    validator = VALIDATORS.get(kind)
    if validator is None:
        return {"ok": False, "errors": [f"Неизвестный тип объекта раскладки: {kind}."], "warnings": []}
    errors, warnings = validator(envelope)
    return {"ok": not errors, "errors": errors, "warnings": warnings}


# --- Рантайм-чтение опубликованной раскладки (ТЗ §3) ------------------------
def _order_val(data: dict[str, Any]) -> float:
    try:
        return float(data.get("order"))
    except (TypeError, ValueError):
        return 0.0


def published_layout() -> dict[str, Any]:
    """Опубликованная раскладка профиля для рантайма: вкладки (с их блоками) и
    оформление. Только status=published; аддитивно — пустые списки, если ничего
    не опубликовано (профиль тогда работает на дефолтной раскладке)."""
    published = [i for i in _store.list(status=STATUS_PUBLISHED)]
    tabs_raw = [i for i in published if (i.get("data") or {}).get("_kind") == KIND_TAB]
    blocks_raw = [i for i in published if (i.get("data") or {}).get("_kind") == KIND_BLOCK]
    themes_raw = [i for i in published if (i.get("data") or {}).get("_kind") == KIND_THEME]
    settings_raw = [i for i in published if (i.get("data") or {}).get("_kind") == KIND_SETTINGS]

    blocks_by_tab: dict[str, list[dict[str, Any]]] = {}
    for env in sorted(blocks_raw, key=lambda e: _order_val(e.get("data") or {})):
        data = env.get("data") or {}
        tab = str(data.get("tab") or "").strip()
        blocks_by_tab.setdefault(tab, []).append({
            "id": env.get("id"),
            "type": data.get("block_type"),
            "name": data.get("name"),
            "order": data.get("order"),
            "width": data.get("width"),
            "visibility": data.get("visibility"),
            "hint": data.get("hint"),
            "show_pc": data.get("show_pc", True),
            "show_mobile": data.get("show_mobile", True),
            "show_player": data.get("show_player", True), "show_admin": data.get("show_admin", True), "hide_player": bool(data.get("hide_player")), "condition": data.get("condition"), "empty_text": data.get("empty_text"),
        })

    tabs: list[dict[str, Any]] = []
    for env in sorted(tabs_raw, key=lambda e: _order_val(e.get("data") or {})):
        data = env.get("data") or {}
        key = str(data.get("tab_key") or env.get("id") or "").strip()
        tabs.append({
            "id": env.get("id"),
            "key": key,
            "label": data.get("label"),
            "icon": data.get("icon"),
            "order": data.get("order"),
            "visibility": data.get("visibility"),
            "default": bool(data.get("default_tab")),
            "show_pc": data.get("show_pc", True),
            "show_mobile": data.get("show_mobile", True),
            "show_player": data.get("show_player", True), "show_admin": data.get("show_admin", True), "hide_player": bool(data.get("hide_player")), "condition": data.get("condition"), "empty_text": data.get("empty_text"),
            "blocks": blocks_by_tab.get(key, []),
        })

    theme = None
    if themes_raw:
        td = themes_raw[0].get("data") or {}
        theme = {k: td.get(k) for k in (
            "title", "profile_background", "tab_background", "card_background",
            "button_color", "text_color", "border_color", "active_tab_color",
            "icon_style", "card_style", "modal_style",
            "primary_color", "secondary_color", "background_color", "positive_color", "negative_color", "warning_color", "danger_color", "border_style", "border_radius", "icon_size", "item_image_size", "compact_mode", "detailed_mode",
        ) if td.get(k)}

    settings = None
    if settings_raw:
        chosen = next((e for e in settings_raw if (e.get("data") or {}).get("is_default")), settings_raw[-1])
        settings = {k: v for k, v in (chosen.get("data") or {}).items() if not str(k).startswith("_")}
    return {"tabs": tabs, "theme": theme, "settings": settings}


def where_used(object_id: str) -> list[dict[str, Any]]:
    """Где используется объект раскладки (ТЗ §6): блоки, привязанные к вкладке."""
    oid = str(object_id or "").strip()
    if not oid:
        return []
    target = _store.get(oid)
    keys = {oid}
    if target is not None:
        tab_key = str((target.get("data") or {}).get("tab_key") or "").strip()
        if tab_key:
            keys.add(tab_key)
    refs: list[dict[str, Any]] = []
    for env in _store.list():
        data = env.get("data") or {}
        if str(data.get("_kind") or "") == KIND_BLOCK and str(data.get("tab") or "").strip() in keys and str(data.get("tab") or "").strip():
            refs.append({"id": env.get("id"), "kind": KIND_BLOCK, "name": str(data.get("name") or env.get("id")), "fields": ["блок на вкладке"]})
    return refs
