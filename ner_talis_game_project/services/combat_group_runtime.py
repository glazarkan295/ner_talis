"""Published combat-group participants and ally turns (ТЗ §72–§77, §85)."""

from __future__ import annotations

import random
from typing import Any


PLAYER_ALLY_TYPES = {"player_ally", "npc_ally", "summon", "clone", "temporary_companion", "shadow"}
PLAYER_SIDES = {"player", "player_allies", "pvp_initiator"}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _bool(value: Any, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "да"}


def _published_npc_ally(ally_id: str) -> dict[str, Any]:
    try:
        from services import npc_ally_constructor_service as allies
        from services.constructor_status import STATUS_PUBLISHED
        env = allies.store().get(ally_id)
        if env and env.get("status") == STATUS_PUBLISHED:
            return dict(env.get("data") or {})
    except Exception:
        pass
    return {}


def attach_participants(battle: dict[str, Any], player: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Materialise player-side allies from the resolved published combat profile."""
    profile = battle.get("combat_profile") if isinstance(battle.get("combat_profile"), dict) else {}
    result: list[dict[str, Any]] = []
    participant_rows = list(profile.get("participants") or [])
    if isinstance(player, dict):
        try:
            from services.npc_ally_runtime import battle_snapshots
            participant_rows.extend(battle_snapshots(player, mode="pve"))
        except Exception:
            pass
    for row in participant_rows:
        if not isinstance(row, dict):
            continue
        ptype = str(row.get("participant_type") or "")
        side = str(row.get("side") or "")
        if ptype not in PLAYER_ALLY_TYPES or side not in PLAYER_SIDES:
            continue
        source_id = str(row.get("source_id") or "")
        source = _published_npc_ally(source_id) if ptype == "npc_ally" else {}
        maximum = max(1, _int(row.get("hp"), _int(source.get("hp"), 50)))
        result.append({
            "participant_id": str(row.get("participant_id") or source_id),
            "participant_type": ptype, "side": side, "team": row.get("team"),
            "source_id": source_id, "name": row.get("name") or source.get("name") or source_id,
            "current_hp": maximum, "max_hp": maximum,
            "mana": _int(row.get("mana"), _int(source.get("mana"))),
            "spirit": _int(row.get("spirit"), _int(source.get("spirit"))),
            "energy": _int(row.get("energy"), _int(source.get("energy"))),
            "damage": max(1, _int(row.get("damage"), max(1, _int(source.get("level"), 1) * 3))),
            "accuracy": max(1, _int(row.get("accuracy"), _int(source.get("accuracy"), 75))),
            "behavior": row.get("behavior") or source.get("target_mode") or "auto",
            "target_priority": row.get("target_priority") or source.get("target_priority") or [],
            "order": _int(row.get("order"), _int(source.get("speed"))),
            "skills": row.get("skills") or source.get("skills") or [],
            "own_actions": row.get("own_actions") or source.get("own_actions") or [],
            "effects": row.get("effects") or source.get("effects") or [],
            "can_target": _bool(row.get("can_target"), True),
            "can_attack": _bool(row.get("can_attack"), "attack" in (source.get("abilities") or []) or not source),
            "can_heal": _bool(row.get("can_heal"), "heal" in (source.get("abilities") or [])),
            "can_use_items": _bool(row.get("can_use_items")),
            "can_escape": _bool(row.get("can_escape")),
            "can_die": _bool(row.get("can_die"), bool(source.get("can_die", True))),
            "victory_reward": row.get("victory_reward"),
            "death_consequence": row.get("death_consequence"),
        })
    result.sort(key=lambda item: item.get("order", 0), reverse=True)
    battle["allies"] = result
    return result


def alive_allies(battle: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in (battle.get("allies") or []) if isinstance(row, dict) and _int(row.get("current_hp")) > 0]


def choose_enemy_target(battle: dict[str, Any], rng: random.Random) -> dict[str, Any] | None:
    """Choose a targetable ally; ``None`` means the main player."""
    candidates = [row for row in alive_allies(battle) if row.get("can_target")]
    if not candidates:
        return None
    protectors = [row for row in candidates if str(row.get("behavior")) == "protect_player"]
    if protectors:
        return protectors[0]
    rule = str((battle.get("combat_profile") or {}).get("enemy_target_rule") or "random")
    if rule == "weakest":
        return min(candidates, key=lambda row: _int(row.get("current_hp")))
    # The player remains a legal target; allies receive part of incoming attacks.
    return rng.choice([None, *candidates])


def damage_ally(ally: dict[str, Any], damage: int, log: list[str], enemy_name: str) -> None:
    before = _int(ally.get("current_hp"))
    ally["current_hp"] = max(0, before - max(0, damage))
    log.append(f"👹 {enemy_name} атакует союзника {ally.get('name')} и наносит {before - ally['current_hp']} урона.")
    if before > 0 and ally["current_hp"] <= 0:
        consequence = str(ally.get("death_consequence") or "").strip()
        suffix = f" Последствие: {consequence}." if consequence else ""
        log.append(f"💀 Союзник {ally.get('name')} погибает.{suffix}")


def apply_ally_phase(battle: dict[str, Any], rng: random.Random, log: list[str]) -> None:
    """Allies heal or attack according to authored behaviour and ordering."""
    enemies = [row for row in (battle.get("enemies") or []) if _int(row.get("current_hp")) > 0]
    player = battle.setdefault("player_state", {})
    for ally in alive_allies(battle):
        behavior = str(ally.get("behavior") or "auto")
        actions = [row for row in (ally.get("own_actions") or []) if isinstance(row, dict)]
        action = sorted(actions, key=lambda row: _int(row.get("priority")), reverse=True)[0] if actions else None
        if action and rng.random() * 100 <= max(0, min(100, _int(action.get("success_chance"), 100))):
            kind = str(action.get("type") or "")
            power = max(1, _int(action.get("power") or action.get("damage") or action.get("amount"), _int(ally.get("damage"))))
            if action.get("formula_id"):
                try:
                    from services.formula_runtime import evaluate
                    power = max(1, _int(evaluate(action.get("formula_id"), {"base_amount": power, "ally_level": ally.get("level", 1)}, default=power), power))
                except Exception:
                    pass
            if kind == "heal":
                current, maximum = _int(player.get("current_hp")), max(1, _int(player.get("max_hp"), 1))
                player["current_hp"] = min(maximum, current + power)
                log.append(str(action.get("success_text") or f"🤝 {ally.get('name')} применяет «{action.get('name') or action.get('id')}» и лечит {player['current_hp'] - current} HP."))
                continue
            if kind in {"attack", "debuff", "finish_enemy", "stop_escape"} and enemies:
                target = min(enemies, key=lambda row: _int(row.get("current_hp"))) if behavior == "weakest" else enemies[0]
                target["current_hp"] = max(0, _int(target.get("current_hp")) - power)
                log.append(str(action.get("success_text") or f"🤝 {ally.get('name')} применяет «{action.get('name') or action.get('id')}»: {power} урона."))
                enemies = [row for row in enemies if _int(row.get("current_hp")) > 0]
                continue
        if ally.get("can_heal") and behavior in {"heal_allies", "protect_player"}:
            current, maximum = _int(player.get("current_hp")), max(1, _int(player.get("max_hp"), 1))
            if current < maximum:
                amount = max(1, _int(ally.get("damage")) // 2)
                player["current_hp"] = min(maximum, current + amount)
                log.append(f"🤝 {ally.get('name')} лечит игрока на {player['current_hp'] - current} HP.")
                continue
        if not ally.get("can_attack") or not enemies:
            continue
        if behavior == "weakest":
            target = min(enemies, key=lambda row: _int(row.get("current_hp")))
        elif behavior == "most_dangerous":
            target = max(enemies, key=lambda row: _int(row.get("base_damage"), _int(row.get("level"))))
        else:
            target = enemies[0]
        if rng.random() * 100 > max(1, _int(ally.get("accuracy"), 75)):
            log.append(f"🤝 {ally.get('name')} промахивается по цели {target.get('name')}.")
            continue
        damage = max(1, _int(ally.get("damage")))
        target["current_hp"] = max(0, _int(target.get("current_hp")) - damage)
        log.append(f"🤝 {ally.get('name')} атакует {target.get('name')} и наносит {damage} урона.")
        enemies = [row for row in enemies if _int(row.get("current_hp")) > 0]


def pvp_allies(profile: dict[str, Any], owner: str, side: str, player_rows: list[dict[str, Any]] | None = None,
                helper_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Materialise authored NPC allies plus invited player-allies for one PVP side."""
    wanted = {"pvp_initiator", "player_allies"} if side == "challenger" else {"pvp_defender", "enemy_allies"}
    output: list[dict[str, Any]] = []
    for row in profile.get("participants") or []:
        if not isinstance(row, dict) or str(row.get("side") or "") not in wanted:
            continue
        ptype = str(row.get("participant_type") or "")
        if ptype not in {"npc_ally", "enemy_npc_ally", "summon", "clone", "temporary_companion", "shadow"}:
            continue
        source_id = str(row.get("source_id") or "")
        source = _published_npc_ally(source_id) if ptype in {"npc_ally", "enemy_npc_ally"} else {}
        hp = max(1, _int(row.get("hp"), _int(source.get("hp"), 40)))
        output.append({"id": str(row.get("participant_id") or source_id), "owner": owner,
                       "type": ptype, "name": row.get("name") or source.get("name") or source_id,
                       "hp": hp, "max_hp": hp, "damage": max(1, _int(row.get("damage"), _int(source.get("level"), 1) * 3)),
                       "behavior": row.get("behavior") or "auto", "source_id": source_id})
    for player in player_rows or []:
        gid = str(player.get("game_id") or player.get("id") or "")
        if gid and gid != owner:
            hp = max(1, _int(player.get("hp"), 100))
            output.append({"id": gid, "owner": owner, "type": "player_ally", "name": player.get("name") or gid,
                           "hp": hp, "max_hp": hp, "damage": max(1, _int(player.get("pvp_damage"), 10)), "behavior": "auto"})
    for row in helper_rows or []:
        hp = max(1, _int(row.get("hp"), 40)); source_id = str(row.get("source_id") or row.get("participant_id") or "")
        output.append({"id": str(row.get("participant_id") or source_id), "owner": owner, "type": "npc_ally",
                       "name": row.get("name") or source_id, "hp": hp, "max_hp": hp,
                       "damage": max(1, _int(row.get("damage"), 5)), "behavior": row.get("behavior") or "auto", "source_id": source_id})
    return output


def pvp_ally_attacks(allies: list[dict[str, Any]], target: dict[str, Any], rng: random.Random) -> list[str]:
    log: list[str] = []
    for ally in allies:
        if _int(ally.get("hp")) <= 0 or _int(target.get("hp")) <= 0:
            continue
        damage = max(1, _int(ally.get("damage")))
        target["hp"] = max(0, _int(target.get("hp")) - damage)
        log.append(f"Союзник {ally.get('name')} наносит {damage} урона.")
    return log
