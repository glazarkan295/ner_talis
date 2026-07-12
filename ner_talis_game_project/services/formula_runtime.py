"""Safe live resolver for formulas published in the admin constructor."""

from __future__ import annotations

from typing import Any

from services import formula_constructor_service as formulas


def numeric_context(values: dict[str, Any] | None = None, *, player: dict[str, Any] | None = None) -> dict[str, float]:
    """Build the numeric-only context accepted by the AST evaluator."""
    out: dict[str, float] = {}
    if isinstance(player, dict):
        aliases = {
            "player_level": player.get("level", 1),
            "level": player.get("level", 1),
            "experience": player.get("experience", player.get("exp", 0)),
            "coins": player.get("coins", player.get("money", 0)),
            "energy": player.get("energy", 0),
            "hp": player.get("hp", player.get("health", 0)),
            "max_hp": player.get("max_hp", player.get("max_health", 0)),
        }
        values = {**aliases, **(values or {})}
    for key, value in (values or {}).items():
        try:
            if isinstance(value, bool):
                continue
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def evaluate(formula_id: Any, values: dict[str, Any] | None = None, *, default: Any = None) -> Any:
    """Evaluate a published formula, returning ``default`` on missing/invalid data."""
    fid = str(formula_id or "").strip()
    if not fid:
        return default
    envelope = formulas.store().get(fid)
    if not envelope or envelope.get("status") != formulas.STATUS_PUBLISHED:
        return default
    data = envelope.get("data") or {}
    env: dict[str, Any] = {}
    for row in data.get("variables") or []:
        if isinstance(row, dict) and str(row.get("key") or "").strip():
            env[str(row["key"]).strip()] = row.get("default", 0)
    env.update(values or {})
    try:
        result = formulas.test_formula(data, env)
    except (ArithmeticError, TypeError, ValueError):
        return default
    return result.get("result") if result.get("ok") else default


def resolve(data: dict[str, Any] | None, field: str, values: dict[str, Any] | None = None, *, default: Any = None) -> Any:
    """Resolve ``<field>_formula_id`` and fall back to the fixed ``field`` value."""
    row = data or {}
    fallback = row.get(field, default)
    return evaluate(row.get(f"{field}_formula_id"), values, default=fallback)


def validate_references(data: dict[str, Any] | None, fields: tuple[str, ...]) -> list[str]:
    """Return publication errors for missing or non-published formula links."""
    errors: list[str] = []
    for field in fields:
        formula_id = str((data or {}).get(field) or "").strip()
        if not formula_id:
            continue
        envelope = formulas.store().get(formula_id)
        if not envelope:
            errors.append(f"Формула {formula_id} из поля {field} не найдена.")
        elif envelope.get("status") != formulas.STATUS_PUBLISHED:
            errors.append(f"Формула {formula_id} из поля {field} не опубликована.")
    return errors
