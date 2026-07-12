"""Конструктор уровней (чат-ТЗ «уровни/опыт/регистрация/расы»).

Запись = определение уровня: требуемый опыт, награды (очки характеристик/навыков),
заголовок, разблокировки. Слой данных + валидация; хранение — EntityStore
(data/level_constructor.json). Существующая формула опыта/уровня — в рантайме
(derived_stats_service); конструктор задаёт табличные параметры по уровням.
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")

_store = EntityStore(
    env_var="LEVEL_CONSTRUCTOR_PATH",
    default_rel="data/level_constructor.json",
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


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    level = _num(data.get("level"))
    if str(data.get("entity_type") or "level") == "level" and (level is None or level < 1):
        errors.append("Уровень должен быть целым ≥ 1.")
    if str(data.get("entity_type") or "level") == "rule":
        if not data.get("active_rule"): errors.append("Правило прогрессии не отмечено активным.")
        if _num(data.get("max_level")) is None or int(data.get("max_level") or 0) < int(data.get("start_level") or 1): errors.append("Максимальный уровень меньше стартового.")
    for key in ("exp_required", "stat_points", "skill_points"):
        if data.get(key) in (None, ""):
            continue
        val = _num(data.get(key))
        if val is None or val < 0:
            errors.append(f"Поле «{key}» не может быть отрицательным.")

    title = str(data.get("title") or "").strip()
    if title and (_HTML_RE.search(title) or "<script" in title.lower()):
        errors.append("В поле «title» недопустим HTML.")
    from services.formula_runtime import validate_references
    errors.extend(validate_references(data, ("formula_id", "exp_formula_id", "stat_points_formula_id", "skill_points_formula_id", "death_loss_formula_id")))
    if str(data.get("entity_type") or "level") == "level":
        previous=[r for r in store().list(status=STATUS_PUBLISHED) if int((r.get("data") or {}).get("level") or 0)<int(level or 0)]  # noqa: F405
        if previous and int(data.get("exp_required") or 0)<=max(int((r.get("data") or {}).get("exp_required") or 0) for r in previous):errors.append("Опыт следующего уровня должен быть больше предыдущего.")
        if not data.get("level_up_text"):warnings.append("Не заполнен текст повышения уровня.")
        if not any((data.get(k) for k in ("stat_points","skill_points","rewards","unlocks"))):warnings.append("Для уровня не настроены награды.")
    if data.get("migration_required") is not True:warnings.append("Изменение прогрессии действующих игроков требует проверки миграции.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}

def active_rule() -> dict[str, Any]:
    rows=[]
    for env in store().list(status=STATUS_PUBLISHED):  # noqa: F405
        data=env.get("data") or {}
        if str(data.get("entity_type") or "level")=="rule" and data.get("active_rule"):rows.append({"id":env.get("id"),**data})
    rows.sort(key=lambda x:int(x.get("priority") or 0),reverse=True)
    return rows[0] if rows else {}

def level_definition(level:int)->dict[str,Any]:
    for env in store().list(status=STATUS_PUBLISHED):  # noqa: F405
        data=env.get("data") or {}
        if str(data.get("entity_type") or "level")=="level" and int(data.get("level") or 0)==int(level):return {"id":env.get("id"),**data}
    return {}
