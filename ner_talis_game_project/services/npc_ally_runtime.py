"""Player-owned NPC helpers lifecycle (ТЗ 2.0 §50–§67)."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def definition(ally_id: str) -> dict[str, Any] | None:
    from services import npc_ally_constructor_service as svc
    from services.constructor_status import STATUS_PUBLISHED
    env = svc.store().get(str(ally_id or ""))
    return dict(env.get("data") or {}) if env and env.get("status") == STATUS_PUBLISHED else None


def _bucket(player: dict[str, Any]) -> dict[str, Any]:
    bucket = player.setdefault("npc_helpers", {})
    if not isinstance(bucket, dict):
        bucket = {}; player["npc_helpers"] = bucket
    bucket.setdefault("owned", {}); bucket.setdefault("history", [])
    return bucket


def grant(player: dict[str, Any], ally_id: str, *, source: str, permanent: bool | None = None,
          now: datetime | None = None) -> dict[str, Any]:
    data = definition(ally_id)
    if not data:
        raise ValueError("NPC-помощник не опубликован или не найден.")
    bucket = _bucket(player); owned = bucket["owned"]
    existing = owned.get(ally_id)
    if isinstance(existing, dict):
        return existing
    moment = now or _now()
    duration = max(0, _int(data.get("duration_seconds") or data.get("time_limit_seconds")))
    is_permanent = bool(data.get("permanent", duration <= 0)) if permanent is None else bool(permanent)
    loyalty_min, loyalty_max = _int(data.get("loyalty_min")), max(_int(data.get("loyalty_min")), _int(data.get("loyalty_max"), 100))
    state = {
        "ally_id": ally_id, "source": source, "obtained_at": _iso(moment), "active": bool(data.get("active_on_receive")),
        "permanent": is_permanent, "expires_at": None if is_permanent or not duration else _iso(moment + timedelta(seconds=duration)),
        "status": "active" if data.get("active_on_receive") else "available",
        "level": max(1, _int(data.get("dev_level") or data.get("level"), 1)), "experience": 0,
        "loyalty": max(loyalty_min, min(loyalty_max, _int(data.get("loyalty_start"), loyalty_min))),
        "battles_used": 0, "actions_used": 0, "cooldowns": {},
    }
    owned[ally_id] = state; bucket["history"].append({"at": _iso(moment), "ally_id": ally_id, "event": "grant", "source": source})
    return state


def _expired(state: dict[str, Any], moment: datetime) -> bool:
    raw = str(state.get("expires_at") or "")
    if not raw: return False
    try: return moment >= datetime.fromisoformat(raw)
    except ValueError: return False


def refresh(player: dict[str, Any], *, now: datetime | None = None) -> None:
    moment = now or _now()
    for state in _bucket(player)["owned"].values():
        if not isinstance(state, dict): continue
        if _expired(state, moment): state.update({"active": False, "status": "expired"})
        if state.get("status") == "recovering" and state.get("recover_at"):
            try: ready = moment >= datetime.fromisoformat(str(state["recover_at"]))
            except ValueError: ready = False
            if ready: state.update({"active": False, "status": "available", "recover_at": None})


def access_error(player: dict[str, Any], ally_id: str) -> str | None:
    data = definition(ally_id) or {}; state = _bucket(player)["owned"].get(ally_id) or {}
    if state.get("status") not in {"available", "active"}: return str(data.get("use_denied_text") or "Помощник сейчас недоступен.")
    if _int(player.get("level"), 1) < _int(data.get("required_level")): return str(data.get("denied_text") or "Недостаточный уровень.")
    zone = str(player.get("current_zone") or player.get("current_location") or "")
    if data.get("forbid_city") and zone.startswith("seldar"): return str(data.get("use_denied_text") or "Помощника нельзя использовать в городе.")
    if data.get("forbid_fortress") and zone.startswith("fortress"): return str(data.get("use_denied_text") or "Помощника нельзя использовать в крепости.")
    try:
        from services.fine_service import active_fines
        if data.get("forbid_with_fine") and active_fines(player): return str(data.get("use_denied_text") or "Помощник недоступен при активном штрафе.")
    except Exception: pass
    if data.get("loyalty_enabled") and _int(state.get("loyalty")) < _int(data.get("required_loyalty")): return str(data.get("use_denied_text") or "Недостаточно лояльности.")
    return None


def activate(player: dict[str, Any], ally_id: str) -> dict[str, Any]:
    refresh(player); bucket = _bucket(player); state = bucket["owned"].get(ally_id)
    if not isinstance(state, dict): raise ValueError("Этот NPC-помощник не принадлежит игроку.")
    denied = access_error(player, ally_id)
    if denied: raise ValueError(denied)
    data = definition(ally_id) or {}; maximum = max(1, _int(data.get("max_active_helpers"), 1))
    active = [row for row in bucket["owned"].values() if isinstance(row, dict) and row.get("active") and row is not state]
    if len(active) >= maximum: raise ValueError(str(data.get("use_denied_text") or f"Можно активировать не больше {maximum} помощников."))
    state.update({"active": True, "status": "active"}); return state


def active_helpers(player: dict[str, Any], *, mode: str = "pve") -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    refresh(player); out = []
    for ally_id, state in _bucket(player)["owned"].items():
        if not isinstance(state, dict) or not state.get("active") or state.get("status") != "active": continue
        data = definition(ally_id)
        if not data: continue
        if mode == "pve" and data.get("pve_enabled") is False: continue
        if mode == "pvp" and str(data.get("pvp_allow_mode") or "forbidden") == "forbidden": continue
        out.append((ally_id, data, state))
    return out


def battle_snapshots(player: dict[str, Any], *, mode: str = "pve") -> list[dict[str, Any]]:
    rows = []
    for ally_id, data, state in active_helpers(player, mode=mode):
        level = max(1, _int(state.get("level"), 1)); hp = max(1, _int(data.get("hp"), 20 + level * 10))
        rows.append({"participant_id": ally_id, "participant_type": "npc_ally", "side": "player_allies",
                     "source_id": ally_id, "name": data.get("name") or ally_id, "hp": hp,
                     "damage": max(1, _int(data.get("phys_damage")) + _int(data.get("magic_damage")) or level * 3),
                     "accuracy": _int(data.get("accuracy"), 75), "behavior": data.get("default_behavior") or data.get("target_mode") or "auto",
                     "order": _int(data.get("initiative") or data.get("speed")), "can_target": data.get("can_be_target", True),
                     "can_attack": "attack" in (data.get("abilities") or []) or bool(data.get("phys_damage") or data.get("magic_damage")),
                     "can_heal": "heal" in (data.get("abilities") or []), "can_escape": bool(data.get("can_escape")),
                     "can_die": bool(data.get("can_die")), "death_consequence": data.get("death_effect_id") or data.get("death_text"),
                     "own_actions": data.get("own_actions") or []})
    return rows


def record_battle(player: dict[str, Any], battle: dict[str, Any], *, victory: bool) -> None:
    by_id = {str(row.get("participant_id") or ""): row for row in battle.get("allies") or [] if isinstance(row, dict)}
    for ally_id, data, state in active_helpers(player):
        state["battles_used"] = _int(state.get("battles_used")) + 1
        state["experience"] = _int(state.get("experience")) + max(0, _int(data.get("dev_exp_per_battle")))
        if data.get("loyalty_enabled"):
            delta = _int(data.get("loyalty_on_victory"), 1) if victory else -max(0, _int(data.get("loyalty_on_defeat"), 1))
            state["loyalty"] = max(_int(data.get("loyalty_min")), min(_int(data.get("loyalty_max"), 100), _int(state.get("loyalty")) + delta))
        snap = by_id.get(ally_id)
        if snap and _int(snap.get("current_hp")) <= 0 and data.get("can_die"):
            if data.get("permanent_death"): state.update({"active": False, "status": "dead"})
            else:
                seconds = max(0, _int(data.get("revival_seconds") or data.get("cooldown_seconds")))
                state.update({"active": False, "status": "recovering", "recover_at": _iso(_now() + timedelta(seconds=seconds)) if seconds else _iso()})
        maximum = _int(data.get("dev_max_level"))
        if data.get("has_levels") and (not maximum or _int(state.get("level")) < maximum):
            need = max(1, _int(data.get("exp_per_level"), 100 * _int(state.get("level"), 1)))
            if _int(state.get("experience")) >= need:
                state["experience"] -= need; state["level"] = _int(state.get("level"), 1) + 1


def outside_action(player: dict[str, Any], ally_id: str, action: str, *, rng: random.Random | None = None) -> str:
    data = definition(ally_id); state = _bucket(player)["owned"].get(ally_id)
    if not data or not isinstance(state, dict) or not state.get("active"): raise ValueError("Активный помощник не найден.")
    if action not in (data.get("out_of_battle_actions") or []): raise ValueError(str(data.get("outside_fail_text") or "Помощник не умеет это действие."))
    cooldowns = state.setdefault("cooldowns", {}); now = _now()
    raw = str(cooldowns.get(action) or "")
    try:
        if raw and now < datetime.fromisoformat(raw): raise ValueError(str(data.get("outside_fail_text") or "Действие ещё восстанавливается."))
    except ValueError as exc:
        if raw: raise exc
    chance = max(0, min(100, _int(data.get("outside_action_chance"), 100)))
    if (rng or random.Random()).random() * 100 >= chance: return str(data.get("outside_fail_text") or "Помощнику не удалось выполнить действие.")
    cooldowns[action] = _iso(now + timedelta(seconds=max(0, _int(data.get("outside_action_cooldown")))))
    state["actions_used"] = _int(state.get("actions_used")) + 1
    if action == "carry_items": player["helper_extra_inventory_slots"] = max(_int(player.get("helper_extra_inventory_slots")), _int(data.get("carry_slots"), 1))
    elif action == "speed_rest": player["helper_rest_speed_percent"] = max(_int(player.get("helper_rest_speed_percent")), _int(data.get("outside_bonus_percent"), 10))
    elif action == "help_craft": player["helper_craft_bonus_percent"] = max(_int(player.get("helper_craft_bonus_percent")), _int(data.get("outside_bonus_percent"), 10))
    elif action == "open_sublocation" and data.get("outside_target_id"): player.setdefault("unlocks", {})[str(data["outside_target_id"])] = True
    elif action == "find_resources": player.setdefault("helper_pending_resources", []).append(str(data.get("outside_target_id") or "random"))
    return str(data.get("outside_success_text") or data.get("outside_action_text") or f"{data.get('name') or ally_id} выполняет действие.")
