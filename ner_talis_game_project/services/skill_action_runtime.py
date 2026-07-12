"""Constructor skill conditions and non-damage actions (§15–§24)."""

from __future__ import annotations

from typing import Any
import time

from services.derived_stats_service import safe_int


NON_DAMAGE_ACTIONS = {"heal", "restore_hp", "restore_mana", "restore_spirit", "restore_energy", "apply_effect", "remove_effect", "cleanse"}


def action_type(skill: dict[str, Any]) -> str:
    return str(skill.get("action_type") or skill.get("skill_action") or ("damage" if str(skill.get("damage_type") or "none") != "none" else "utility"))


def can_use(player: dict[str, Any], skill: dict[str, Any], *, in_battle: bool) -> tuple[bool, str]:
    if in_battle and skill.get("works_in_battle") is False:
        return False, str(skill.get("text_wrong_context") or "Навык нельзя использовать в бою.")
    if not in_battle and not skill.get("works_outside_battle"):
        return False, str(skill.get("text_wrong_context") or "Навык работает только в бою.")
    required_state = str(skill.get("required_player_state") or "")
    if required_state and not player.get(required_state):
        return False, str(skill.get("text_wrong_state") or "Состояние игрока не позволяет применить навык.")
    forbidden_state = str(skill.get("forbidden_player_state") or "")
    if forbidden_state and player.get(forbidden_state):
        return False, str(skill.get("text_wrong_state") or "Состояние игрока блокирует навык.")
    required_book = str(skill.get("required_magic_book_id") or "")
    if required_book:
        equipped = player.get("equipment") or {}
        ids = {str(row.get("item_id") or row.get("id") or "") for row in equipped.values() if isinstance(row, dict)}
        if required_book not in ids:
            return False, str(skill.get("text_missing_book") or "Для навыка требуется магическая книга.")
    required_hand = str(skill.get("required_hand") or "")
    if required_hand:
        from services.effect_runtime_service import blocked_slots
        blocked = blocked_slots(player)
        aliases = {"left": {"weapon2", "left_hand"}, "right": {"weapon", "right_hand"}, "both": {"weapon", "weapon2", "left_hand", "right_hand"}}
        if any(slot in blocked for slot in aliases.get(required_hand, {required_hand})):
            return False, str(skill.get("text_hand_trauma") or "Травма руки блокирует этот навык.")
    return True, ""


def cooldown_turns(player: dict[str, Any], skill: dict[str, Any]) -> int:
    value = max(0, safe_int(skill.get("cooldown_turns", skill.get("cooldown")), 0))
    try:
        from services.effect_runtime_service import effect_fields, _definition
        for field in effect_fields():
            for row in player.get(field) or []:
                if isinstance(row, dict):
                    data = _definition(row)
                    value += safe_int(data.get("skill_cooldown_flat", data.get("cooldown_increase_turns")), 0)
    except Exception:
        pass
    return max(0, value)


def _amount(player: dict[str, Any], skill: dict[str, Any], key: str, formula_key: str) -> int:
    base = max(0, safe_int(skill.get(key), 0))
    from services.formula_runtime import evaluate, numeric_context
    return max(0, safe_int(evaluate(skill.get(formula_key), numeric_context({"base_amount": base, "item_level": skill.get("level", 1)}, player=player), default=base), base))


def apply_non_damage(player: dict[str, Any], skill: dict[str, Any]) -> dict[str, Any]:
    action = action_type(skill)
    messages: list[str] = []
    changed: dict[str, int] = {}
    resource_key = {"heal": "hp", "restore_hp": "hp", "restore_mana": "mana", "restore_spirit": "spirit", "restore_energy": "energy"}.get(action)
    if resource_key:
        amount = _amount(player, skill, f"{resource_key}_amount", f"{resource_key}_formula_id")
        maximum = safe_int(player.get(f"max_{resource_key}"), safe_int(player.get(resource_key), 0) + amount)
        before = safe_int(player.get(resource_key), 0)
        player[resource_key] = min(maximum, before + amount)
        changed[resource_key] = player[resource_key] - before
        messages.append(f"{resource_key.upper()} восстановлено: {changed[resource_key]}.")
    for effect_id in skill.get("apply_effect_ids") or ([skill.get("apply_effect_id")] if skill.get("apply_effect_id") else []):
        from services.effect_formula_runtime import apply_to_player
        if apply_to_player(player, str(effect_id), source="skill", context={"skill_id": skill.get("id")}):
            messages.append(f"Наложен эффект: {effect_id}.")
    remove_ids = {str(x) for x in skill.get("remove_effect_ids") or ([skill.get("remove_effect_id")] if skill.get("remove_effect_id") else []) if x}
    if remove_ids:
        for field in ("active_effects", "active_curses"):
            player[field] = [row for row in player.get(field) or [] if not isinstance(row, dict) or str(row.get("effect_id") or row.get("id") or "") not in remove_ids]
        messages.append("Эффекты сняты.")
    return {"action": action, "changed": changed, "text": " ".join(messages) or str(skill.get("bot_text") or "Навык применён.")}


def use_outside_battle(player: dict[str, Any], skill_id: str) -> dict[str, Any]:
    from services.active_skill_service import resource_cost_with_modifiers, consume_skill_ammo
    target = str(skill_id or "")
    skill = next((row for section in ("active", "equipped", "passive", "passive_equipped")
                  for row in (player.get("skills") or {}).get(section, [])
                  if isinstance(row, dict) and target in {str(row.get("id") or ""), str(row.get("name") or "")}), None)
    if not skill:
        raise ValueError("Навык не изучен игроком.")
    ok, message = can_use(player, skill, in_battle=False)
    if not ok:
        raise ValueError(message)
    now = time.time()
    cooldowns = player.setdefault("skill_cooldowns_until", {})
    until = float(cooldowns.get(str(skill_id)) or 0)
    if until > now:
        raise ValueError(f"Навык ещё на откате: {max(1, round(until - now))} сек.")
    resource = str(skill.get("resource_type") or skill.get("resource") or "none")
    base_cost = safe_int(skill.get("resource_cost", skill.get("base_resource_cost")), 0)
    if resource in {"mana", "spirit"}:
        spirit_cost, mana_cost = resource_cost_with_modifiers(skill, player)
        cost = mana_cost if resource == "mana" else spirit_cost
    else:
        from services.formula_runtime import evaluate, numeric_context
        cost = max(0, safe_int(evaluate(skill.get("use_cost_formula_id"), numeric_context({"base_amount": base_cost}, player=player), default=base_cost), base_cost))
    if resource != "none" and safe_int(player.get(resource), 0) < cost:
        raise ValueError(f"Недостаточно ресурса «{resource}»: нужно {cost}.")
    ammo_ok, ammo_text = consume_skill_ammo(player, skill)
    if not ammo_ok:
        raise ValueError(ammo_text)
    if resource != "none":
        player[resource] = max(0, safe_int(player.get(resource), 0) - cost)
    result = apply_non_damage(player, skill)
    seconds = max(0, safe_int(skill.get("cooldown_seconds"), cooldown_turns(player, skill)))
    if seconds:
        cooldowns[str(skill_id)] = now + seconds
    result["resource_cost"] = {resource: cost} if resource != "none" else {}
    result["ammo_text"] = ammo_text
    return result


def choose_mob_skill(enemy: dict[str, Any], rng: Any) -> dict[str, Any] | None:
    mob_id = str(enemy.get("source_mob_id") or "")
    if not mob_id:
        return None
    from services.skill_constructor_service import store
    cooldowns = enemy.setdefault("skill_cooldowns", {})
    for key in list(cooldowns):
        cooldowns[key] = max(0, safe_int(cooldowns[key], 0) - 1)
        if cooldowns[key] <= 0:
            cooldowns.pop(key, None)
    authored=[]
    removed={str(value) for value in enemy.get("removed_phase_skill_ids") or []}
    allowed_add={str(value) for value in enemy.get("added_phase_skill_ids") or []}
    for data in enemy.get("constructor_mob_skills") or []:
        skill_id=str(data.get("id") or "")
        if skill_id in removed or data.get("active") is False or cooldowns.get(skill_id):continue
        condition=str(data.get("use_condition") or "always");hp=safe_int(enemy.get("current_hp"),0);maximum=max(1,safe_int(enemy.get("max_hp"),1))
        if condition in {"low_hp","hp_below_50"} and hp*100/maximum>=50:continue
        if condition in {"critical_hp","hp_below_25"} and hp*100/maximum>=25:continue
        if allowed_add and skill_id not in allowed_add and data.get("phase_only"):continue
        authored.append(data)
    authored.sort(key=lambda row:safe_int(row.get("priority"),0),reverse=True)
    for data in authored:
        if rng.randint(1,100)>max(0,min(100,safe_int(data.get("use_chance"),100))):continue
        skill_id=str(data.get("id") or "");cooldowns[skill_id]=max(0,safe_int(data.get("cooldown"),0))
        return {"name":data.get("name") or skill_id,"mob_use_chance":data.get("use_chance"),"cooldown_turns":data.get("cooldown"),**data}
    for row in store().list(status="published"):
        data = row.get("data") or {}
        if str(data.get("source_type") or "") != "mob" or str(data.get("linked_mob_id") or "") != mob_id:
            continue
        skill_id = str(row.get("id") or "")
        if cooldowns.get(skill_id):
            continue
        if rng.randint(1, 100) > max(0, min(100, safe_int(data.get("mob_use_chance"), 100))):
            continue
        cooldowns[skill_id] = max(0, safe_int(data.get("cooldown_turns"), 0))
        return {"id": skill_id, **data}
    return None
