"""Published repair rules for the crafting constructor (§17)."""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403

_HTML_RE = re.compile(r"<[^>]+>")
_store = EntityStore(env_var="REPAIR_CONSTRUCTOR_PATH", default_rel="data/repair_constructor.json",
                     statuses=STATUSES, transitions=TRANSITIONS, initial_status=STATUS_DRAFT)  # noqa: F405


def store() -> EntityStore:
    return _store


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []
    if not str(data.get("name") or "").strip():
        errors.append("Не заполнено название правила ремонта.")
    for key in ("repair_percent", "success_chance", "break_risk"):
        if data.get(key) in (None, ""):
            continue
        try:
            value = float(data[key])
        except (TypeError, ValueError):
            errors.append(f"Поле «{key}» должно быть числом.")
            continue
        if key != "repair_percent" and not 0 <= value <= 100:
            errors.append(f"Поле «{key}» должно быть 0–100.")
        if key == "repair_percent" and value <= 0:
            errors.append("Процент ремонта должен быть больше нуля.")
    for key in ("name", "description", "success_text", "fail_text"):
        value = str(data.get(key) or "")
        if value and (_HTML_RE.search(value) or "<script" in value.lower()):
            errors.append(f"В поле «{key}» недопустим HTML.")
    from services.formula_runtime import validate_references
    errors.extend(validate_references(data, ("success_formula_id", "repair_formula_id", "break_risk_formula_id")))
    return {"ok": not errors, "errors": errors, "warnings": warnings}
