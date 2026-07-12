"""Level and experience progression helpers."""

from __future__ import annotations

import math
from typing import Any

from services.race_bonus_service import experience_multiplier
from services.active_skill_service import maybe_mark_branch_hint


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def experience_to_next_level(level: int) -> int:
    level = max(1, safe_int(level, 1))
    fallback = level * 100
    try:
        from services import level_constructor_service as levels
        from services.formula_runtime import evaluate
        rows = levels.store().list(status=levels.STATUS_PUBLISHED)
        exact = next((row for row in rows if safe_int((row.get("data") or {}).get("level"), 0) == level), None)
        if exact:
            data = exact.get("data") or {}
            fixed = safe_int(data.get("exp_required"), fallback)
            value = evaluate(data.get("exp_formula_id") or data.get("formula_id"), {
                "player_level": level, "level": level, "base_amount": fixed,
            }, default=fixed)
            return max(1, safe_int(value, fixed))
        # A generic published level formula may define the entire curve.
        generic = next((row for row in rows if (row.get("data") or {}).get("formula_id")), None)
        if generic:
            value = evaluate((generic.get("data") or {}).get("formula_id"), {
                "player_level": level, "level": level, "base_amount": fallback,
            }, default=fallback)
            return max(1, safe_int(value, fallback))
    except Exception:
        pass
    return max(100, fallback)


LEVEL_UP_STAT_POINTS = 5
LEVEL_UP_SKILL_POINTS = 2


def _process_level_ups(player: dict[str, Any]) -> int:
    """Spend accumulated experience on level-ups. Shared by all xp grants.

    Centralising the level-up rewards (stat/skill points per level) keeps the
    normal gameplay grant and the admin "exact experience" grant from drifting
    apart if the rewards-per-level ever change.
    """

    level_ups = 0
    try:
        from services.level_constructor_service import active_rule
        rule=active_rule()
    except Exception:rule={}
    max_level=max(1,safe_int(rule.get("temporary_level_cap") or rule.get("max_level"),10**9))
    while True:
        level = max(1, safe_int(player.get("level"), 1))
        if level>=max_level:
            if rule.get("burn_exp_after_cap"):player["experience"]=0
            elif rule.get("convert_exp_after_cap") and player.get("experience"):
                player["cap_experience"]=safe_int(player.get("cap_experience"))+safe_int(player.get("experience"));player["experience"]=0
            player["experience_to_next"]=0;break
        required = experience_to_next_level(level)
        if safe_int(player.get("experience"), 0) < required:
            player["experience_to_next"] = required
            break
        player["experience"] = safe_int(player.get("experience"), 0) - required
        player["level"] = level + 1
        try:
            from services.level_constructor_service import level_definition
            definition=level_definition(level+1)
        except Exception:definition={}
        stat_points=safe_int(definition.get("stat_points"),safe_int(rule.get("stat_points_per_level"),LEVEL_UP_STAT_POINTS))
        skill_points=safe_int(definition.get("skill_points"),safe_int(rule.get("skill_points_per_level"),LEVEL_UP_SKILL_POINTS))
        try:
            from services.formula_runtime import evaluate
            stat_points=safe_int(evaluate(definition.get("stat_points_formula_id") or rule.get("stat_points_formula_id"),{"level":level+1,"player_level":level+1,"base_amount":stat_points},default=stat_points),stat_points)
            skill_points=safe_int(evaluate(definition.get("skill_points_formula_id") or rule.get("skill_points_formula_id"),{"level":level+1,"player_level":level+1,"base_amount":skill_points},default=skill_points),skill_points)
        except Exception:pass
        player["free_stat_points"] = safe_int(player.get("free_stat_points"), 0) + max(0,stat_points)
        player["free_skill_points"] = safe_int(player.get("free_skill_points"), 0) + max(0,skill_points)
        for unlock in definition.get("unlocks") or []:player.setdefault("unlocks",{})[str(unlock)]=True
        for reward in definition.get("rewards") or []:
            if not isinstance(reward,dict):continue
            kind=str(reward.get("type") or "");oid=str(reward.get("object_id") or "");amount=max(1,safe_int(reward.get("amount"),1))
            if kind=="currency":player["money"]=safe_int(player.get("money"))+amount
            elif kind=="energy":player["energy"]=safe_int(player.get("energy"))+amount
            elif kind=="item" and oid:
                try:
                    from services.inventory_service import add_inventory_item
                    from services.item_registry import build_inventory_item
                    add_inventory_item(player,build_inventory_item(oid,amount,item_id=oid),amount,default_source="level_up")
                except Exception:pass
            elif kind in ("effect","achievement") and oid:player.setdefault("level_rewards",[]).append({"type":kind,"id":oid,"level":level+1})
            elif kind in ("location","skill","quest") and oid:player.setdefault("unlocks",{})[oid]=True
        player.setdefault("level_up_messages",[]).append(str(definition.get("level_up_text") or rule.get("level_up_text") or f"Достигнут уровень {level+1}."))
        level_ups += 1
    return level_ups


def grant_exact_experience(player: dict[str, Any], amount: int) -> dict[str, Any]:
    """Grant experience 1:1 (no race multiplier) and process level-ups.

    Used by admin tools/promocodes where 1 unit must equal exactly 1 experience.
    """

    gained = max(0, safe_int(amount, 0))
    player["experience"] = max(0, safe_int(player.get("experience"), 0)) + gained
    player["total_experience"] = max(0, safe_int(player.get("total_experience"), 0)) + gained
    level_ups = _process_level_ups(player)
    return {
        "gained": gained,
        "level_ups": level_ups,
        "level": max(1, safe_int(player.get("level"), 1)),
        "experience": safe_int(player.get("experience"), 0),
        "experience_to_next": safe_int(player.get("experience_to_next"), experience_to_next_level(max(1, safe_int(player.get("level"), 1)))),
    }


def grant_experience(player: dict[str, Any], base_amount: int, *, source_type: str | None = None,
                     context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Grant experience with the player's race multiplier, then process level-ups."""

    base_amount = max(0, safe_int(base_amount, 0))
    if source_type:
        from services.experience_runtime import resolve,source_settings
        base_amount = resolve(source_type, base_amount, player=player, context=context)
        authored=source_settings(source_type,context)
    else:authored={}
    gained = int(math.ceil(base_amount * (experience_multiplier(player) if authored.get("use_race",True) is not False else 1)))
    player["experience"] = max(0, safe_int(player.get("experience"), 0)) + gained
    player["total_experience"] = max(0, safe_int(player.get("total_experience"), 0)) + gained

    level_ups = _process_level_ups(player)

    branch_hint = maybe_mark_branch_hint(player) if level_ups > 0 else None
    return {
        "gained": gained,
        "level_ups": level_ups,
        "level": max(1, safe_int(player.get("level"), 1)),
        "experience": safe_int(player.get("experience"), 0),
        "experience_to_next": safe_int(player.get("experience_to_next"), experience_to_next_level(max(1, safe_int(player.get("level"), 1)))),
        "branch_hint": branch_hint,
    }


def apply_death_experience_penalty(player: dict[str, Any], percent: int = 10) -> dict[str, int]:
    """Remove a percentage of the level's required experience after death.

    Default death penalty is 10% of the maximum experience available on the
    player's current level, not 10% of the currently filled progress bar. The
    penalty never lowers the player's level and never drops current experience
    below zero. ``total_experience`` stays as lifetime earned experience and is
    not reduced.
    """

    try:
        from services.level_constructor_service import active_rule
        rule=active_rule()
    except Exception:rule={}
    if rule and not rule.get("death_exp_loss_enabled",True):percent=0
    elif rule:percent=safe_int(rule.get("death_loss_percent"),percent)
    percent = max(0, safe_int(percent, 0))
    current = max(0, safe_int(player.get("experience"), 0))
    level = max(1, safe_int(player.get("level"), 1))
    required = experience_to_next_level(level)
    base=current if rule.get("death_loss_from_current") else required
    lost = 0 if current <= 0 or percent <= 0 else max(1, math.ceil(base * percent / 100))
    try:
        from services.formula_runtime import evaluate
        lost=safe_int(evaluate(rule.get("death_loss_formula_id"),{"base_amount":lost,"player_level":level,"current_experience":current,"experience_to_next":required},default=lost),lost)
    except Exception:pass
    if rule.get("death_loss_min") not in (None,""):lost=max(safe_int(rule.get("death_loss_min")),lost)
    if rule.get("death_loss_max") not in (None,"") and safe_int(rule.get("death_loss_max"))>0:lost=min(safe_int(rule.get("death_loss_max")),lost)
    lost = min(current, lost)
    player["experience"] = max(0, current - lost)
    player["experience_to_next"] = required
    player["last_death_experience_penalty"] = lost
    return {
        "lost": lost,
        "percent": percent,
        "base_experience": required,
        "experience": safe_int(player.get("experience"), 0),
        "experience_to_next": safe_int(player.get("experience_to_next"), required),
    }
