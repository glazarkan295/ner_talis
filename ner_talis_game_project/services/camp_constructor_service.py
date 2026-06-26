"""Конструктор лагеря V2 (доп. ТЗ §4) — авторская часть.

Лагерь — отдельная настраиваемая механика отдыха игрока в локациях: текст,
восстановление (HP/мана/дух/энергия), время отдыха, доступные действия, особые
события, привязка к локациям. Это слой данных + валидация; рантайм отдыха —
services/external_location_service.py (лагерь/готовка). Хранение — генерик
EntityStore (data/camp_constructor.json). Аудит и права (camp.*) — в роутере
admin_camp_api. Существующие лагеря заводятся constructor_import.import_camps.
"""

from __future__ import annotations

import re
from typing import Any

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

# --- Справочники (доп. ТЗ §4) -----------------------------------------------
CAMP_TYPES = ("standard", "safe", "dangerous", "event", "temporary", "special")
CAMP_TYPE_LABELS = {
    "standard": "Стандартный", "safe": "Безопасный", "dangerous": "Опасный",
    "event": "Событийный", "temporary": "Временный", "special": "Специальный",
}
RECOVERY_TARGETS = ("hp", "mana", "spirit", "energy", "stamina", "fatigue")
CAMP_ACTIONS = (
    "rest", "restore_hp", "restore_energy", "restore_mana", "restore_spirit",
    "inspect", "cook", "use_item", "talk_npc", "check_gear", "special_event",
    "leave", "back",
)

_HTML_RE = re.compile(r"<[^>]+>")

_store = EntityStore(
    env_var="CAMP_CONSTRUCTOR_PATH",
    default_rel="data/camp_constructor.json",
    statuses=STATUSES,
    transitions=TRANSITIONS,
    initial_status=STATUS_DRAFT,
)


def store() -> EntityStore:
    return _store


def _str(data: dict[str, Any], key: str) -> str:
    return str(data.get(key) or "").strip()


def _has_markup(value: str) -> bool:
    return "<script" in value.lower() or bool(_HTML_RE.search(value))


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    """Проверка лагеря перед публикацией (доп. ТЗ §4.2–§4.6)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not _str(data, "name"):
        errors.append("Не заполнено название лагеря.")
    camp_type = _str(data, "camp_type")
    if camp_type and camp_type not in CAMP_TYPES:
        errors.append(f"Неизвестный тип лагеря: {camp_type}.")

    # Восстановление (§4.3).
    recovery = data.get("recovery")
    if isinstance(recovery, list):
        for i, row in enumerate(recovery, start=1):
            if not isinstance(row, dict):
                errors.append(f"Восстановление {i}: неверный формат.")
                continue
            target = str(row.get("target") or "").strip()
            if target and target not in RECOVERY_TARGETS:
                errors.append(f"Восстановление {i}: неизвестная цель «{target}».")
            for key in ("flat", "percent", "per_minute", "min", "max"):
                val = _num(row.get(key))
                if val is not None and val < 0:
                    errors.append(f"Восстановление {i}: «{key}» не может быть отрицательным.")
            mn = _num(row.get("min"))
            mx = _num(row.get("max"))
            if mn is not None and mx is not None and mn > mx:
                errors.append(f"Восстановление {i}: мин. больше макс.")
    elif recovery not in (None, ""):
        errors.append("Восстановление должно быть списком.")

    # Время (§4.4).
    for key in ("base_time", "min_time", "max_time", "cooldown", "use_limit"):
        val = _num(data.get(key))
        if data.get(key) not in (None, "") and (val is None or val < 0):
            errors.append(f"Поле «{key}» не может быть отрицательным.")
    min_t = _num(data.get("min_time"))
    max_t = _num(data.get("max_time"))
    if min_t is not None and max_t is not None and min_t > max_t:
        errors.append("Минимальное время больше максимального.")

    # Действия (§4.5).
    actions = data.get("actions")
    if isinstance(actions, list):
        for act in actions:
            if str(act) not in CAMP_ACTIONS:
                warnings.append(f"Действие «{act}» не из стандартного списка.")

    for key in ("name", "full_text", "short_description"):
        value = _str(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def published_for_location(location_id: str) -> list[dict[str, Any]]:
    """Опубликованные лагеря, привязанные к локации (для выбора в конструкторе
    локаций, §4.8)."""
    lid = str(location_id or "").strip()
    out: list[dict[str, Any]] = []
    for env in _store.list(status=STATUS_PUBLISHED):
        data = env.get("data") or {}
        locs = data.get("locations") or []
        if not lid or (isinstance(locs, list) and lid in [str(x) for x in locs]):
            out.append({"id": env.get("id"), "name": data.get("name"), "camp_type": data.get("camp_type")})
    return out
