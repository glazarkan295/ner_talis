"""Live resolver for published experience-source constructor entries."""

from __future__ import annotations

from typing import Any

def source_settings(source_type:str,context:dict[str,Any]|None=None)->dict[str,Any]:
    try:
        from services import exp_constructor_service as sources
        rows=[];target=str((context or {}).get("source_id") or (context or {}).get("mob_id") or (context or {}).get("quest_id") or "")
        for env in sources.store().list(status=sources.STATUS_PUBLISHED):
            data=env.get("data") or {}
            if str(data.get("source_type") or "")!=str(source_type or ""):continue
            authored=str(data.get("source_id") or "")
            if authored and authored!=target:continue
            rows.append(data)
        rows.sort(key=lambda d:(bool(d.get("source_id")),int(d.get("priority") or 0)),reverse=True)
        return rows[0] if rows else {}
    except Exception:return {}


def resolve(source_type: str, base_amount: Any, *, player: dict[str, Any] | None = None,
            context: dict[str, Any] | None = None) -> int:
    try:
        base = max(0, int(float(base_amount or 0)))
    except (TypeError, ValueError):
        base = 0
    try:
        from services import exp_constructor_service as sources
        data=source_settings(source_type,context)
        if not data:
            # Совместимый проектный fallback до публикации authored-источника.
            if str(source_type)=="mob_kill" and int((player or {}).get("level") or 1)>=10:return max(0,int(base*.7))
            return base
        level = max(1, int((player or {}).get("level") or 1))
        scaling = float(data.get("level_scaling_percent") or 0)
        fixed = data.get("base_exp")
        seed = base if base_amount is not None else max(0, int(float(fixed or 0)))
        fallback = seed * (1 + max(0, level - 1) * scaling / 100)
        from services.formula_runtime import evaluate, numeric_context
        value = evaluate(data.get("formula_id"), numeric_context({
            "base_amount": seed, "multiplier": 1 + max(0, level - 1) * scaling / 100,
            **(context or {}),
        }, player=player), default=fallback)
        result=max(0,int(float(value)))
        if data.get("penalty_after_level") and level>=int(data.get("penalty_after_level") or 0):result=int(result*(1-max(0,min(100,float(data.get("penalty_percent") or 0)))/100))
        if data.get("min_exp") not in (None,""):result=max(int(data["min_exp"]),result)
        if data.get("max_exp") not in (None,""):result=min(int(data["max_exp"]),result)
        return max(0,result)
    except (ArithmeticError, TypeError, ValueError):
        return base
