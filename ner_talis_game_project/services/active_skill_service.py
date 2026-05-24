"""Starter-skill helpers for Ner-Talis.

The old branch-based active-skill catalog and Spirit/Mana choice flow are
disabled.  Runtime gameplay keeps only the two neutral starter skills while
retaining small compatibility helpers for older profiles and imports.
"""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

# Full active-skill branch integration is intentionally disabled.
# Only the two starter neutral skills remain available to players.
ACTIVE_SKILL_BRANCH_INTEGRATION_ENABLED = False
STARTER_SKILL_IDS = {"basic_attack", "magic_spark"}
STARTER_SKILL_NAMES = {"Обычный удар", "Магический сгусток"}
DISABLED_BRANCH_TEXT = (
    "Система ветвей активных навыков сейчас отключена. "
    "Доступны только стартовые действия: «Обычный удар» и «Магический сгусток»."
)

RUS_TO_BACK_ATTRIBUTE = {
    "Сила": "strength",
    "Выносливость": "endurance",
    "Ловкость": "dexterity",
    "Восприятие": "perception",
    "Интеллект": "intelligence",
    "Мудрость": "wisdom",
    "str": "strength",
    "end": "endurance",
    "agi": "dexterity",
    "dex": "dexterity",
    "per": "perception",
    "int": "intelligence",
    "wis": "wisdom",
}

PROFILE_ATTRIBUTE_KEYS = {
    "str": "strength",
    "end": "endurance",
    "agi": "dexterity",
    "dex": "dexterity",
    "per": "perception",
    "int": "intelligence",
    "wis": "wisdom",
    "strength": "strength",
    "endurance": "endurance",
    "dexterity": "dexterity",
    "perception": "perception",
    "intelligence": "intelligence",
    "wisdom": "wisdom",
}


def load_active_skill_registry() -> dict[str, Any]:
    """Compatibility stub: branch catalog files are no longer part of runtime."""
    return {"skills": [], "counts": {}}


def load_active_skill_counts() -> dict[str, Any]:
    """Compatibility stub: branch catalog files are no longer part of runtime."""
    return {}


def load_branch_choice_messages() -> dict[str, Any]:
    """Compatibility stub for removed branch-choice messages."""
    return {}


def all_catalog_skills() -> list[dict[str, Any]]:
    """Return runtime catalog skills.

    The branch-based active skill catalog is no longer integrated into the
    game runtime.  Keep this function for compatibility with old imports, but
    never expose branch skills or unlock them automatically.
    """
    return []


def catalog_skill_by_id(skill_id: str) -> dict[str, Any] | None:
    """Compatibility stub for the removed active-skill registry."""
    return None


def skill_level(skill: dict[str, Any]) -> int:
    modifiers = skill.get("modifiers")
    if isinstance(modifiers, list) and modifiers:
        total = 1
        for modifier in modifiers:
            if isinstance(modifier, dict):
                total += int(modifier.get("level") or modifier.get("points") or 0)
        return max(1, total)
    return int(skill.get("level") or 0)


def find_player_skill(player: dict[str, Any], skill_id: str) -> dict[str, Any] | None:
    skills = player.get("skills") if isinstance(player.get("skills"), dict) else {}
    target = str(skill_id or "")
    for section in ("active", "equipped", "passive"):
        for skill in skills.get(section, []) if isinstance(skills.get(section), list) else []:
            if not isinstance(skill, dict):
                continue
            if target in {str(skill.get("id") or ""), str(skill.get("name") or "")}:
                return skill
    return None


def get_player_skill_level(player: dict[str, Any], skill_id: str) -> int:
    skill = find_player_skill(player, skill_id)
    return skill_level(skill) if skill else 0


def get_modifier_level(player: dict[str, Any], skill_id: str, modifier_name: str) -> int:
    skill = find_player_skill(player, skill_id)
    if not skill:
        return 0
    target = str(modifier_name or "")
    for modifier in skill.get("modifiers", []) if isinstance(skill.get("modifiers"), list) else []:
        if not isinstance(modifier, dict):
            continue
        if target in {str(modifier.get("id") or ""), str(modifier.get("name") or ""), str(modifier.get("label") or "")}:
            return int(modifier.get("level") or modifier.get("points") or 0)
    return 0


def player_branch(player: dict[str, Any]) -> str | None:
    """Branch development is disabled; no runtime profile has a branch."""
    return None


def normalize_starter_only_skills(player: dict[str, Any]) -> bool:
    """Remove disabled branch skills while preserving starter skills.

    Older profiles may still contain skills granted by the removed Spirit/Mana
    branch system.  Keeping them in ``equipped`` would let the battle router use
    disabled actions, so we strip every non-starter active/equipped skill.
    """
    skills = player.get("skills")
    if not isinstance(skills, dict):
        return False

    changed = False
    for section in ("active", "equipped"):
        values = skills.get(section)
        if not isinstance(values, list):
            skills[section] = []
            changed = True
            continue
        kept = []
        for skill in values:
            if not isinstance(skill, dict):
                changed = True
                continue
            skill_id = str(skill.get("id") or "")
            skill_name = str(skill.get("name") or "")
            if skill_id in STARTER_SKILL_IDS or skill_name in STARTER_SKILL_NAMES:
                kept.append(skill)
            else:
                changed = True
        if kept != values:
            skills[section] = kept
            changed = True

    # Passive skills are not part of the removed active-branch integration.
    if not isinstance(skills.get("passive"), list):
        skills["passive"] = []
        changed = True

    for field in ("skill_branch", "active_skill_branch", "branch_chosen_at", "branch_choice_place"):
        if player.get(field) is not None:
            player[field] = None
            changed = True
    if player.get("branch") not in {None, "Без ветви", "Ветви отключены"}:
        player["branch"] = "Без ветви"
        changed = True
    if player.get("branch_choice_hint_sent"):
        player["branch_choice_hint_sent"] = False
        changed = True
    return changed


def has_identification_amulet(player: dict[str, Any]) -> bool:
    if player.get("has_identification_amulet") is True:
        return True
    # The registration text states that every registered player receives this
    # amulet. Old profiles may not have an explicit flag, so completed profiles
    # are treated as owning it unless a future system says otherwise.
    return bool(player.get("starter_pack_applied") or player.get("created_at"))


def ensure_active_skill_fields(player: dict[str, Any]) -> bool:
    """Keep only compatibility skill containers and starter skills.

    The old Spirit/Mana branch fields are neutralized instead of being removed
    abruptly, so older stored profiles can still be loaded safely.
    """
    changed = False
    if player.get("skill_branch") is not None:
        player["skill_branch"] = None
        changed = True
    if player.get("active_skill_branch") is not None:
        player["active_skill_branch"] = None
        changed = True
    if player.get("branch") not in {None, "Без ветви", "Ветви отключены"}:
        player["branch"] = "Без ветви"
        changed = True
    if player.get("branch_choice_hint_sent"):
        player["branch_choice_hint_sent"] = False
        changed = True
    if player.get("branch_chosen_at") is not None:
        player["branch_chosen_at"] = None
        changed = True
    if player.get("branch_choice_place") is not None:
        player["branch_choice_place"] = None
        changed = True
    if "has_identification_amulet" not in player:
        player["has_identification_amulet"] = True
        changed = True
    skills = player.setdefault("skills", {})
    if not isinstance(skills, dict):
        player["skills"] = skills = {"active": [], "passive": [], "equipped": []}
        changed = True
    for section in ("active", "passive", "equipped"):
        if not isinstance(skills.get(section), list):
            skills[section] = []
            changed = True
    return normalize_starter_only_skills(player) or changed


def _modifier_id(name: str, index: int) -> str:
    return f"mod_{index + 1}"


def runtime_skill_from_catalog(skill: dict[str, Any]) -> dict[str, Any]:
    skill = deepcopy(skill)
    resource = str(skill.get("resource") or "none")
    cost = max(0, int(skill.get("base_resource_cost") or 0))
    damage_type = str(skill.get("damage_type") or "none")
    if damage_type == "magical":
        damage_type = "magic"
    modifiers: list[dict[str, Any]] = []
    for index, modifier in enumerate(skill.get("modifiers", []) if isinstance(skill.get("modifiers"), list) else []):
        if not isinstance(modifier, dict):
            continue
        modifiers.append(
            {
                "id": str(modifier.get("id") or _modifier_id(str(modifier.get("name") or ""), index)),
                "name": str(modifier.get("name") or f"Модификатор {index + 1}"),
                "type": modifier.get("type"),
                "effect": modifier.get("effect") or "Усиливает навык.",
                "description": modifier.get("effect") or "Усиливает навык.",
                "level": int(modifier.get("level") or 0),
                "unlock_skill_level": modifier.get("unlock_skill_level", 1),
                "max_level": modifier.get("max_level"),
            }
        )
    effects = skill.get("effects") if isinstance(skill.get("effects"), list) else []
    description = " ".join(str(item) for item in effects if item) or str(skill.get("notes") or "Активный навык.")
    return {
        "id": skill.get("id"),
        "name": skill.get("name"),
        "level": 1 if modifiers else 0,
        "skill_type": "active",
        "category": skill.get("category") or "active",
        "role": skill.get("role"),
        "resource_branch": skill.get("resource_branch"),
        "allowed_branches": skill.get("allowed_branches") or [],
        "resource": resource,
        "spirit_cost": cost if resource == "spirit" else 0,
        "mana_cost": cost if resource == "mana" else 0,
        "base_resource_cost": cost,
        "cooldown_turns": int(skill.get("cooldown_turns") or 0),
        "target_mode": skill.get("targeting") or "single_enemy",
        "target": skill.get("targeting") or "single_enemy",
        "damage_type": damage_type,
        "damage_split": skill.get("damage_split") or {},
        "attribute_profile": skill.get("attribute_profile") or {},
        "role_coefficient": float(skill.get("role_coefficient") or 0.5),
        "upgradeable": bool(modifiers),
        "has_modifiers": bool(modifiers),
        "modifiers": modifiers,
        "description": description,
        "bot_text": skill.get("bot_text") or f"Вы применяете навык: «{skill.get('name')}».",
        "unlock": skill.get("unlock") or {},
        "weapon_requirements": skill.get("weapon_requirements") or [],
        "ammo_requirements": skill.get("ammo_requirements") or {},
        "tags": skill.get("tags") or [],
        "not_unlocked_by_player_level": True,
    }


def player_has_skill(player: dict[str, Any], skill_id: str) -> bool:
    return find_player_skill(player, skill_id) is not None


def add_skill_to_player(player: dict[str, Any], skill: dict[str, Any]) -> bool:
    ensure_active_skill_fields(player)
    skill_id = str(skill.get("id") or "")
    if not skill_id or player_has_skill(player, skill_id):
        return False
    player["skills"].setdefault("active", []).append(runtime_skill_from_catalog(skill))
    return True


def branch_starter_skills(branch: str) -> list[dict[str, Any]]:
    return [
        skill for skill in all_catalog_skills()
        if isinstance(skill, dict)
        and str((skill.get("unlock") or {}).get("type") or "") == "branch_starter"
        and str(skill.get("resource_branch") or "") == branch
    ]


WEAPON_SLOT_ORDER = ("weapon1", "weapon2", "shield")


def weapon_token_for_item(item: dict[str, Any] | None) -> str | None:
    """Return the project weapon token represented by an equipped item."""

    if not isinstance(item, dict):
        return None
    explicit = str(item.get("weapon_type") or item.get("weaponToken") or item.get("weapon_token") or "").strip().casefold()
    if explicit in {"sword", "dagger", "staff", "axe", "hammer", "bow", "shield", "crossbow"}:
        return explicit
    text = " ".join(
        str(item.get(key) or "")
        for key in ("type", "subtype", "name", "slot", "slotKey", "targetSlotKey", "category")
    ).casefold()
    if "арбал" in text or "crossbow" in text:
        return "crossbow"
    if "лук" in text or "bow" in text:
        return "bow"
    if "посох" in text or "staff" in text:
        return "staff"
    if "кинжал" in text or "dagger" in text:
        return "dagger"
    if "топор" in text or "axe" in text:
        return "axe"
    if "молот" in text or "hammer" in text or "булав" in text or "mace" in text:
        return "hammer"
    if "щит" in text or "shield" in text:
        return "shield"
    if "меч" in text or "sword" in text:
        return "sword"
    return None


def current_weapon_tokens(player: dict[str, Any]) -> set[str]:
    """Return weapon tokens equipped by the player.

    The active-skill package uses an ``any_of`` list with these project weapon
    types: sword, dagger, staff, axe, hammer, bow, shield and crossbow. ``any``
    means the skill is weapon-independent.
    """
    tokens = {"any"}
    equipment = player.get("equipment") if isinstance(player.get("equipment"), dict) else {}
    for slot in WEAPON_SLOT_ORDER:
        token = weapon_token_for_item(equipment.get(slot))
        if token:
            tokens.add(token)
    return tokens


def equipped_weapon_token_for_skill(player: dict[str, Any], skill: dict[str, Any]) -> str | None:
    """Return the concrete equipped weapon token used by a skill.

    This matters for multi-weapon skills such as «Метка охотника»: if the
    current compatible weapon is a bow/crossbow, the skill must consume ammo;
    if the compatible weapon is a staff/dagger, it does not. The project has no
    separate "selected hand" state, so weapon slots are checked in stable order.
    """

    allowed_raw = skill.get("weapon_requirements") or ["any"]
    if isinstance(allowed_raw, str):
        allowed_raw = [allowed_raw]
    allowed = {str(item) for item in allowed_raw if item}
    if not allowed or "any" in allowed:
        return None
    equipment = player.get("equipment") if isinstance(player.get("equipment"), dict) else {}
    for slot in WEAPON_SLOT_ORDER:
        token = weapon_token_for_item(equipment.get(slot))
        if token and token in allowed:
            return token
    return None


def current_equipment_tokens(player: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    equipment = player.get("equipment") if isinstance(player.get("equipment"), dict) else {}
    for item in equipment.values():
        if not isinstance(item, dict):
            continue
        text = " ".join(str(item.get(key) or "") for key in ("type", "subtype", "name", "slot", "slotKey", "category")).casefold()
        if "тяж" in text or "heavy" in text:
            tokens.add("heavy_armor")
        if "сред" in text or "medium" in text:
            tokens.add("medium_armor")
        if "лёг" in text or "легк" in text or "light" in text:
            tokens.add("light_armor")
        if "ткан" in text or "robe" in text or "cloth" in text:
            tokens.add("cloth_armor")
        if "щит" in text or "shield" in text:
            tokens.add("shield")
    return tokens


def invested_attribute_value(player: dict[str, Any], attribute: str) -> int:
    key = RUS_TO_BACK_ATTRIBUTE.get(str(attribute or ""), str(attribute or ""))
    invested = player.get("invested_stats") if isinstance(player.get("invested_stats"), dict) else {}
    return int(invested.get(key) or 0)


def check_skill_requirement(player: dict[str, Any], requirement: dict[str, Any]) -> bool:
    if not isinstance(requirement, dict):
        return False
    kind = requirement.get("kind")
    branch = player_branch(player)
    if kind in {"player_registered", "starter_action"}:
        return True
    if kind == "branch_choice":
        return branch == requirement.get("branch")
    if kind == "branch_choice_required":
        return branch in set(requirement.get("allowed_branches") or [])
    if kind == "required_skill_level":
        return get_player_skill_level(player, str(requirement.get("skill_id") or "")) >= int(requirement.get("skill_level") or 0)
    if kind == "any_required_skill_level":
        return any(
            get_player_skill_level(player, str(option.get("skill_id") or "")) >= int(option.get("skill_level") or 0)
            for option in requirement.get("options", []) if isinstance(option, dict)
        )
    if kind == "required_modifier_level":
        return get_modifier_level(player, str(requirement.get("skill_id") or ""), str(requirement.get("modifier_name") or "")) >= int(requirement.get("modifier_level") or 0)
    if kind == "invested_attribute":
        return invested_attribute_value(player, str(requirement.get("attribute") or "")) >= int(requirement.get("threshold") or 0)
    if kind == "weapon_type":
        allowed_raw = requirement.get("allowed") or []
        if isinstance(allowed_raw, str):
            allowed_raw = [allowed_raw]
        allowed = {str(item) for item in allowed_raw}
        if not allowed:
            return True
        tokens = current_weapon_tokens(player)
        return bool(tokens & allowed) or "any" in allowed
    if kind == "equipment_type":
        allowed_raw = requirement.get("allowed") or []
        if isinstance(allowed_raw, str):
            allowed_raw = [allowed_raw]
        allowed = {str(item) for item in allowed_raw}
        return bool(current_equipment_tokens(player) & allowed)
    if kind == "weapon_or_equipment_type":
        allowed_weapons = requirement.get("allowed_weapons") or []
        allowed_equipment = requirement.get("allowed_equipment") or []
        if isinstance(allowed_weapons, str):
            allowed_weapons = [allowed_weapons]
        if isinstance(allowed_equipment, str):
            allowed_equipment = [allowed_equipment]
        weapon_allowed = {str(item) for item in allowed_weapons}
        equipment_allowed = {str(item) for item in allowed_equipment}
        return (
            "any" in weapon_allowed
            or bool(current_weapon_tokens(player) & weapon_allowed)
            or bool(current_equipment_tokens(player) & equipment_allowed)
        )
    if kind == "learning_source":
        sources = set(player.get("unlocked_skill_sources") or [])
        return str(requirement.get("source") or "") in sources or "ANY" in sources
    return False


def can_unlock_catalog_skill(player: dict[str, Any], skill: dict[str, Any]) -> bool:
    """Automatic catalog unlocks are disabled."""
    return False





def is_skill_weapon_compatible(player: dict[str, Any], skill: dict[str, Any]) -> bool:
    allowed_raw = skill.get("weapon_requirements") or ["any"]
    if isinstance(allowed_raw, str):
        allowed_raw = [allowed_raw]
    allowed = {str(item) for item in allowed_raw}
    if not allowed or "any" in allowed:
        return True
    return bool(current_weapon_tokens(player) & allowed)


def skill_weapon_requirement_text(skill: dict[str, Any]) -> str:
    allowed_raw = skill.get("weapon_requirements") or ["any"]
    if isinstance(allowed_raw, str):
        allowed_raw = [allowed_raw]
    labels = {
        "any": "любое оружие",
        "sword": "меч",
        "dagger": "кинжал",
        "staff": "посох",
        "axe": "топор",
        "hammer": "молот",
        "bow": "лук",
        "shield": "щит",
        "crossbow": "арбалет",
    }
    return ", ".join(labels.get(str(item), str(item)) for item in allowed_raw)


def _ammo_requirements_for_weapon(skill: dict[str, Any], weapon_token: str | None) -> dict[str, Any] | None:
    ammo = skill.get("ammo_requirements") if isinstance(skill.get("ammo_requirements"), dict) else {}
    if not ammo or ammo.get("enabled") is False or not weapon_token:
        return None
    by_weapon = ammo.get("requirements_by_weapon") if isinstance(ammo.get("requirements_by_weapon"), dict) else {}
    requirement = by_weapon.get(weapon_token)
    return requirement if isinstance(requirement, dict) else None


def skill_ammo_requirement_for_current_weapon(player: dict[str, Any], skill: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    weapon_token = equipped_weapon_token_for_skill(player, skill)
    return weapon_token, _ammo_requirements_for_weapon(skill, weapon_token)


def _quiver_kind(item: dict[str, Any] | None) -> str:
    if not isinstance(item, dict):
        return ""
    item_id = str(item.get("id") or item.get("item_id") or "")
    raw = " ".join(str(item.get(key) or "") for key in ("quiver_type", "subtype", "type", "slot", "slotKey", "targetSlotKey", "name")).casefold()
    if item_id == "arrow_quiver_empty" or "arrow_quiver" in raw or "стрел" in raw:
        return "arrow_quiver"
    if item_id == "bolt_quiver_empty" or "bolt_quiver" in raw or "болт" in raw:
        return "bolt_quiver"
    return "quiver" if "quiver" in raw or "колчан" in raw else ""


def _equipped_quiver(player: dict[str, Any], slot: str) -> dict[str, Any] | None:
    equipment = player.get("equipment") if isinstance(player.get("equipment"), dict) else {}
    weapon2 = equipment.get("weapon2")
    if isinstance(weapon2, dict) and _quiver_kind(weapon2) == slot:
        return weapon2
    item = equipment.get(slot)
    if isinstance(item, dict):
        return item
    equipped_quivers = player.get("equipped_quivers") if isinstance(player.get("equipped_quivers"), dict) else {}
    item = equipped_quivers.get(slot)
    return item if isinstance(item, dict) else None


def validate_skill_ammo(player: dict[str, Any], skill: dict[str, Any]) -> tuple[bool, str]:
    """Check quiver/ammo availability without consuming ammo."""

    _weapon, requirement = skill_ammo_requirement_for_current_weapon(player, skill)
    if not requirement:
        return True, ""
    quiver_requirement = requirement.get("quiver_requirement") if isinstance(requirement.get("quiver_requirement"), dict) else {}
    quiver_slot = str(quiver_requirement.get("quiver_slot") or requirement.get("quiver_slot") or "")
    quiver = _equipped_quiver(player, quiver_slot)
    if not isinstance(quiver, dict):
        return False, str(requirement.get("missing_quiver_message") or quiver_requirement.get("missing_quiver_message") or "Нужен подходящий колчан.")
    required_ammo_id = str(requirement.get("ammo_item_id") or "")
    if required_ammo_id and str(quiver.get("ammo_item_id") or required_ammo_id) != required_ammo_id:
        return False, str(requirement.get("missing_loaded_ammo_message") or "В колчане нет нужных боеприпасов.")
    need = max(1, int(requirement.get("consume_per_use") or 1))
    if int(quiver.get("ammo_count") or 0) < need:
        return False, str(requirement.get("missing_loaded_ammo_message") or requirement.get("missing_message") or "В колчане нет нужного количества боеприпасов.")
    return True, ""


def consume_skill_ammo(player: dict[str, Any], skill: dict[str, Any]) -> tuple[bool, str]:
    """Consume ammo for bow/crossbow skills after validation and before hit roll."""

    _weapon, requirement = skill_ammo_requirement_for_current_weapon(player, skill)
    if not requirement:
        return True, ""
    ok, message = validate_skill_ammo(player, skill)
    if not ok:
        return False, message
    quiver_requirement = requirement.get("quiver_requirement") if isinstance(requirement.get("quiver_requirement"), dict) else {}
    quiver_slot = str(quiver_requirement.get("quiver_slot") or requirement.get("quiver_slot") or "")
    quiver = _equipped_quiver(player, quiver_slot)
    need = max(1, int(requirement.get("consume_per_use") or 1))
    quiver["ammo_count"] = max(0, int(quiver.get("ammo_count") or 0) - need)
    ammo_name = str(requirement.get("ammo_short_name") or requirement.get("ammo_name") or "боеприпас")
    return True, f"Из колчана израсходовано: {ammo_name} ×{need}."
def refresh_unlocked_active_skills(player: dict[str, Any]) -> int:
    """Compatibility no-op for the removed branch active-skill integration."""
    ensure_active_skill_fields(player)
    return 0


def can_choose_active_skill_branch_here(player: dict[str, Any]) -> bool:
    return False


def choose_active_skill_branch(player: dict[str, Any], branch: str) -> dict[str, Any]:
    ensure_active_skill_fields(player)
    raise ValueError("active skill branches are disabled")


def branch_hint_text() -> str:
    return DISABLED_BRANCH_TEXT


def maybe_mark_branch_hint(player: dict[str, Any]) -> str | None:
    ensure_active_skill_fields(player)
    return None


def skill_profile_power(stats: dict[str, Any], profile: dict[str, Any]) -> float:
    total = 0.0
    for raw_key, weight in profile.items():
        key = PROFILE_ATTRIBUTE_KEYS.get(str(raw_key), str(raw_key))
        try:
            total += float(stats.get(key) or 0) * float(weight)
        except (TypeError, ValueError):
            continue
    return total


def skill_modifier_multiplier(skill: dict[str, Any]) -> float:
    multiplier = 1.0
    for modifier in skill.get("modifiers", []) if isinstance(skill.get("modifiers"), list) else []:
        if not isinstance(modifier, dict):
            continue
        level = int(modifier.get("level") or modifier.get("points") or 0)
        text = f"{modifier.get('type') or ''} {modifier.get('effect') or ''}".casefold()
        if level <= 0:
            continue
        if "сила" in text or "урон" in text or "основн" in text:
            multiplier += 0.04 * level
    return max(0.1, multiplier)


def resource_cost_with_modifiers(skill: dict[str, Any]) -> tuple[int, int]:
    base_cost = int(skill.get("base_resource_cost") or skill.get("spirit_cost") or skill.get("mana_cost") or 0)
    reduction = 0.0
    for modifier in skill.get("modifiers", []) if isinstance(skill.get("modifiers"), list) else []:
        if not isinstance(modifier, dict):
            continue
        level = int(modifier.get("level") or modifier.get("points") or 0)
        text = f"{modifier.get('type') or ''} {modifier.get('effect') or ''}".casefold()
        if level > 0 and ("ресурс" in text or "расход" in text or "эконом" in text):
            reduction += 0.02 * level
    cost = max(0, math.ceil(base_cost * max(0.2, 1 - reduction)))
    resource = str(skill.get("resource") or "")
    if resource == "spirit" or int(skill.get("spirit_cost") or 0) > 0:
        return cost, 0
    if resource == "mana" or int(skill.get("mana_cost") or 0) > 0:
        return 0, cost
    return 0, 0
