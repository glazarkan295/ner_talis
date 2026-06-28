"""Конструктор фаз боссов (ТЗ «черты/благословения/фазы» §7, §12.3).

Фаза — набор условий/модификаторов/навыков/текста для босса. Библиотека из 20
универсальных фаз сидируется через constructor_import.import_phases. Слой данных
+ валидация; хранение — EntityStore (data/phase_constructor.json). Аудит/права
(phase.*) — в роутере.
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore

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

# --- Справочники (ТЗ §12.3) -------------------------------------------------
BOSS_RANKS = ("mini_boss", "boss", "raid_boss", "world_boss", "unique")
BOSS_RANK_LABELS = {
    "mini_boss": "Мини-босс", "boss": "Босс", "raid_boss": "Рейдовый босс",
    "world_boss": "Мировой босс", "unique": "Уникальный",
}
TRIGGER_TYPES = ("hp_percent", "turn_count", "time", "objective", "manual",
                 "minion_death", "damage_taken", "custom")
TRIGGER_TYPE_LABELS = {
    "hp_percent": "По % HP", "turn_count": "По числу ходов", "time": "По времени",
    "objective": "По условию", "manual": "Вручную", "minion_death": "Смерть помощников",
    "damage_taken": "Полученный урон", "custom": "Своё",
}

_HTML_RE = re.compile(r"<[^>]+>")

_store = EntityStore(
    env_var="PHASE_CONSTRUCTOR_PATH",
    default_rel="data/phase_constructor.json",
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
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not _str(data, "phase_name"):
        errors.append("Не заполнено название фазы.")
    trigger = _str(data, "trigger_type")
    if trigger and trigger not in TRIGGER_TYPES:
        errors.append(f"Неизвестный тип триггера: {trigger}.")

    ranks = data.get("allowed_boss_ranks")
    if isinstance(ranks, list):
        for r in ranks:
            if str(r) not in BOSS_RANKS:
                errors.append(f"Неизвестный ранг босса: {r}.")
    elif ranks not in (None, ""):
        errors.append("Список рангов боссов должен быть списком.")

    for key in ("trigger_value", "phase_duration_turns", "phase_duration_seconds"):
        val = _num(data.get(key))
        if data.get(key) not in (None, "") and (val is None or val < 0):
            errors.append(f"Поле «{key}» не может быть отрицательным.")
    if trigger == "hp_percent":
        hp = _num(data.get("trigger_value"))
        if hp is not None and (hp < 0 or hp > 100):
            errors.append("Для триггера по % HP значение должно быть 0–100.")

    for key in ("phase_name", "phase_text_for_player"):
        value = _str(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
