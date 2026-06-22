"""Конструктор раскладки профиля игрока V2 (ТЗ §3).

Настраивает, ЧТО и в каком порядке игрок видит в своём профиле: вкладки
(profile_tab), блоки внутри вкладок (profile_block) и оформление (profile_theme).
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
KINDS = (KIND_TAB, KIND_BLOCK, KIND_THEME)

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
        warnings.append("Вкладка «Обзор» не используется — распределите данные по другим вкладкам.")
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
    return errors, []


VALIDATORS: dict[str, Callable[[dict[str, Any]], tuple[list[str], list[str]]]] = {
    KIND_TAB: _validate_tab,
    KIND_BLOCK: _validate_block,
    KIND_THEME: _validate_theme,
}


def validate(kind: str, envelope: dict[str, Any]) -> dict[str, Any]:
    validator = VALIDATORS.get(kind)
    if validator is None:
        return {"ok": False, "errors": [f"Неизвестный тип объекта раскладки: {kind}."], "warnings": []}
    errors, warnings = validator(envelope)
    return {"ok": not errors, "errors": errors, "warnings": warnings}
