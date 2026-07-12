"""Resolve formula-backed fields of a published effect definition."""

from __future__ import annotations

from typing import Any
from datetime import datetime, timedelta, timezone
import random

from services.formula_runtime import evaluate, numeric_context


def resolve(effect_id: str, *, player: dict[str, Any] | None = None,
            context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    from services.effect_constructor_service import published_definition
    data = published_definition(effect_id)
    if not data:
        return None
    values = numeric_context({"base_amount": data.get("value", data.get("flat_bonus", data.get("value_percent", 0))),
                              **(context or {})}, player=player)
    if data.get("value_formula_id"):
        value = evaluate(data.get("value_formula_id"), values, default=values.get("base_amount", 0))
        data["value"] = value
        if "flat_bonus" in data: data["flat_bonus"] = value
    if data.get("duration_formula_id"):
        base = data.get("duration_seconds", data.get("duration_turns", 0))
        duration = evaluate(data.get("duration_formula_id"), {**values, "base_amount": base}, default=base)
        if data.get("duration_mode") == "turns" or (data.get("duration_turns") and not data.get("duration_seconds")):
            data["duration_turns"] = max(0, int(float(duration or 0)))
        else:
            data["duration_seconds"] = max(0, int(float(duration or 0)))
    if data.get("chance_formula_id"):
        base = data.get("apply_chance_percent", 100)
        data["apply_chance_percent"] = max(0.0, min(100.0, float(evaluate(data.get("chance_formula_id"), {**values, "base_chance": base, "base_amount": base}, default=base))))
    if data.get("limit_formula_id"):
        base = data.get("max_stacks", 1)
        data["max_stacks"] = max(1, int(float(evaluate(data.get("limit_formula_id"), {**values, "base_amount": base}, default=base) or 1)))
    return data


def apply_to_player(player: dict[str, Any], effect_id: str, *, source: str = "system",
                    context: dict[str, Any] | None = None, rng: random.Random | None = None) -> dict[str, Any] | None:
    data = resolve(effect_id, player=player, context=context)
    if not data:
        payload = {"effect_id": effect_id, "source": source}
        if context and context.get("duration_seconds"):
            duration = max(0, int(float(context["duration_seconds"] or 0)))
            payload["duration_seconds"] = duration
            if duration:
                payload["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=duration)).isoformat()
        player.setdefault("active_effects", []).append(payload)
        try:
            from services.achievement_engine import record_game_event
            record_game_event(player,"gain_effect",1,effect_id)
        except Exception:pass
        return payload
    rng = rng or random.Random()
    if rng.uniform(0, 100) > float(data.get("apply_chance_percent", 100) or 0):
        return None
    payload = {"effect_id": effect_id, "source": source, "constructor_live": True,
               "applied_at": datetime.now(timezone.utc).isoformat(),
               **{k: v for k, v in data.items() if k not in {"admin_description"}}}
    duration = int(float(payload.get("duration_seconds") or 0))
    if duration > 0:
        payload["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=duration)).isoformat()
    if payload.get("duration_turns") not in (None, ""):
        payload["remaining_turns"] = max(0, int(float(payload.get("duration_turns") or 0)))
    field = "active_curses" if payload.get("effect_type") == "curse_effect" or payload.get("effect_category") == "curse" else "active_effects"
    effects = player.setdefault(field, [])
    if not isinstance(effects, list):
        effects = []; player[field] = effects
    same = [row for row in effects if isinstance(row, dict) and str(row.get("effect_id") or row.get("id") or "") == effect_id]
    limit = max(1, int(float(payload.get("max_stacks") or 1)))
    while len(same) >= limit:
        victim = same.pop(0)
        effects.remove(victim)
    effects.append(payload)
    try:
        from services.achievement_engine import record_game_event
        record_game_event(player,"gain_curse" if field=="active_curses" else "gain_effect",1,effect_id)
    except Exception:pass
    return payload
