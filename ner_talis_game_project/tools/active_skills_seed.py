# -*- coding: utf-8 -*-
"""Пример загрузчика активных навыков Нер-Талис.

Важное правило: активные навыки не открываются напрямую за уровень игрока.
Уровень 10 используется только для допуска к выбору ветви у Распорядительного камня.

Луки и арбалеты используют боеприпасы только через экипированные колчаны:
- bow -> arrow_quiver -> arrow_for_bow
- crossbow -> bolt_quiver -> bolt_for_crossbow
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SUPPORTED_WEAPON_TYPES = {"sword", "dagger", "staff", "axe", "hammer", "bow", "shield", "crossbow"}
UNIVERSAL_WEAPON_VALUE = "any"
SUPPORTED_AMMO_TYPES = {"arrow_for_bow", "bolt_for_crossbow"}
SUPPORTED_QUIVER_SLOTS = {"arrow_quiver", "bolt_quiver"}


def load_active_skills(path: str | Path = "active_skills_registry.json") -> dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_skill_by_id(registry: dict[str, Any], skill_id: str) -> dict[str, Any] | None:
    for skill in registry.get("skills", []):
        if skill.get("id") == skill_id:
            return skill
    return None


def get_skill_level(player: Any, skill_id: str) -> int:
    """Ожидаемый формат: player.skills[skill_id]["level"].

    Если в проекте уровень навыка считается динамически по модификаторам,
    замените тело функции на расчёт: 1 + сумма уровней модификаторов.
    """
    return int(getattr(player, "skills", {}).get(skill_id, {}).get("level", 0))


def get_modifier_level(player: Any, skill_id: str, modifier_name: str) -> int:
    skill_state = getattr(player, "skills", {}).get(skill_id, {})
    modifiers = skill_state.get("modifiers", {})
    return int(modifiers.get(modifier_name, 0))


def has_learning_source(player: Any, source_text: str) -> bool:
    """Заглушка под книги, наставников, свитки, квесты, события и особые условия."""
    unlocked_sources = getattr(player, "unlocked_skill_sources", set())
    return source_text in unlocked_sources or "ANY" in unlocked_sources


def can_choose_branch_at_order_stone(player: Any) -> bool:
    """Проверка системного выбора ветви, а не открытия конкретного навыка."""
    return (
        getattr(player, "level", 1) >= 10
        and getattr(player, "skill_branch", None) is None
        and getattr(player, "current_city", None) == "seldar"
        and getattr(player, "current_zone", None) == "town_hall"
        and getattr(player, "current_place", None) == "order_stone"
        and bool(getattr(player, "has_identification_amulet", False))
    )


def get_equipped_weapon_type(player: Any) -> str | None:
    return getattr(player, "equipped_weapon_type", None)


def get_equipped_armor_type(player: Any) -> str | None:
    return getattr(player, "equipped_armor_type", None)


def is_weapon_allowed_for_skill(player: Any, skill: dict[str, Any]) -> bool:
    """Проверка оружия по правилу any_of.

    weapon_requirements всегда считается списком разрешённых типов оружия.
    Навык доступен, если экипирован хотя бы один подходящий тип.
    Значение "any" означает, что действие не зависит от оружия.
    """
    allowed_raw = skill.get("weapon_requirements", [UNIVERSAL_WEAPON_VALUE])
    if isinstance(allowed_raw, str):
        allowed_raw = [allowed_raw]
    allowed = set(allowed_raw)
    if UNIVERSAL_WEAPON_VALUE in allowed:
        return True
    equipped = get_equipped_weapon_type(player)
    return equipped in allowed


def get_equipped_quiver(player: Any, quiver_slot: str) -> Any | None:
    """Возвращает экипированный колчан.

    Поддерживаемые варианты хранения:
    1) player.equipped_quivers[quiver_slot]
    2) player.equipment_slots[quiver_slot]
    3) player.arrow_quiver / player.bolt_quiver
    """
    equipped_quivers = getattr(player, "equipped_quivers", {}) or {}
    if quiver_slot in equipped_quivers:
        return equipped_quivers[quiver_slot]

    equipment_slots = getattr(player, "equipment_slots", {}) or {}
    if quiver_slot in equipment_slots:
        return equipment_slots[quiver_slot]

    return getattr(player, quiver_slot, None)


def _get_value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def quiver_matches_requirement(quiver: Any, rule: dict[str, Any]) -> bool:
    q_req = rule.get("quiver_requirement") or {}
    if not q_req.get("required", False):
        return True
    if quiver is None:
        return False

    expected_slot = q_req.get("quiver_slot")
    expected_id = q_req.get("quiver_item_id")
    aliases = set(q_req.get("quiver_aliases", []))

    quiver_slot = _get_value(quiver, "slot")
    quiver_id = _get_value(quiver, "item_id") or _get_value(quiver, "id")
    quiver_name = _get_value(quiver, "name")

    return (
        quiver_slot == expected_slot
        or quiver_id == expected_id
        or quiver_id in aliases
        or quiver_name in aliases
    )


def get_quiver_ammo_count(quiver: Any, ammo_item_id: str) -> int:
    """Возвращает количество нужного боеприпаса внутри колчана.

    Поддерживаемые варианты:
    - {"ammo_item_id": "arrow_for_bow", "ammo_count": 12}
    - {"loaded_ammo": {"item_id": "arrow_for_bow", "count": 12}}
    - {"contents": {"arrow_for_bow": 12}}
    """
    if quiver is None:
        return 0

    ammo_id = _get_value(quiver, "ammo_item_id")
    ammo_count = _get_value(quiver, "ammo_count")
    if ammo_id == ammo_item_id and ammo_count is not None:
        return int(ammo_count)

    loaded_ammo = _get_value(quiver, "loaded_ammo", {}) or {}
    if _get_value(loaded_ammo, "item_id") == ammo_item_id:
        return int(_get_value(loaded_ammo, "count", 0))

    contents = _get_value(quiver, "contents", {}) or {}
    if isinstance(contents, dict):
        value = contents.get(ammo_item_id, 0)
        if isinstance(value, dict):
            return int(value.get("count", 0))
        return int(value or 0)

    return 0


def set_quiver_ammo_count(quiver: Any, ammo_item_id: str, new_count: int) -> None:
    """Записывает новое количество боеприпасов в колчан."""
    new_count = max(0, int(new_count))
    if isinstance(quiver, dict):
        if quiver.get("ammo_item_id") == ammo_item_id or "ammo_count" in quiver:
            quiver["ammo_item_id"] = ammo_item_id
            quiver["ammo_count"] = new_count
            return
        loaded_ammo = quiver.get("loaded_ammo")
        if isinstance(loaded_ammo, dict):
            loaded_ammo["item_id"] = ammo_item_id
            loaded_ammo["count"] = new_count
            return
        contents = quiver.setdefault("contents", {})
        contents[ammo_item_id] = new_count
        return

    setattr(quiver, "ammo_item_id", ammo_item_id)
    setattr(quiver, "ammo_count", new_count)


def get_current_ammo_rule(player: Any, skill: dict[str, Any]) -> dict[str, Any] | None:
    ammo = skill.get("ammo_requirements") or {}
    if not ammo.get("enabled"):
        return None
    equipped = get_equipped_weapon_type(player)
    return ammo.get("requirements_by_weapon", {}).get(equipped)


def has_required_quiver(player: Any, skill: dict[str, Any]) -> bool:
    """Проверяет наличие подходящего экипированного колчана."""
    rule = get_current_ammo_rule(player, skill)
    if not rule:
        return True
    q_req = rule.get("quiver_requirement") or {}
    if not q_req.get("required", False):
        return True
    quiver = get_equipped_quiver(player, q_req.get("quiver_slot"))
    return quiver_matches_requirement(quiver, rule)


def has_required_ammo(player: Any, skill: dict[str, Any]) -> bool:
    """Проверяет стрелы/болты в подходящем экипированном колчане."""
    rule = get_current_ammo_rule(player, skill)
    if not rule:
        return True
    if not has_required_quiver(player, skill):
        return False
    q_req = rule.get("quiver_requirement") or {}
    quiver = get_equipped_quiver(player, q_req.get("quiver_slot"))
    count = get_quiver_ammo_count(quiver, rule["ammo_item_id"])
    return count >= int(rule.get("consume_per_use", 1))


def get_missing_ammo_or_quiver_message(player: Any, skill: dict[str, Any]) -> str | None:
    rule = get_current_ammo_rule(player, skill)
    if not rule:
        return None
    if not has_required_quiver(player, skill):
        return rule.get("missing_quiver_message") or rule.get("missing_message")
    if not has_required_ammo(player, skill):
        return rule.get("missing_loaded_ammo_message") or rule.get("missing_message")
    return None


def consume_required_ammo(player: Any, skill: dict[str, Any]) -> None:
    """Списывает стрелу/болт из экипированного колчана.

    Функцию нужно вызывать после can_learn_or_use_skill, но до расчёта попадания.
    Если атака промахнулась, боеприпас уже потрачен.
    """
    rule = get_current_ammo_rule(player, skill)
    if not rule:
        return
    q_req = rule.get("quiver_requirement") or {}
    quiver = get_equipped_quiver(player, q_req.get("quiver_slot"))
    if not quiver_matches_requirement(quiver, rule):
        raise ValueError(rule.get("missing_quiver_message", "Missing required quiver"))
    ammo_item_id = rule["ammo_item_id"]
    need = int(rule.get("consume_per_use", 1))
    current = get_quiver_ammo_count(quiver, ammo_item_id)
    if current < need:
        raise ValueError(rule.get("missing_loaded_ammo_message", "Not enough ammo in quiver"))
    set_quiver_ammo_count(quiver, ammo_item_id, current - need)


def check_skill_requirement(player: Any, requirement: dict[str, Any], registry: dict[str, Any]) -> bool:
    kind = requirement.get("kind")

    if kind in {"player_registered", "starter_action"}:
        return True

    if kind == "branch_choice":
        return getattr(player, "skill_branch", None) == requirement.get("branch")

    if kind == "branch_choice_required":
        branch = getattr(player, "skill_branch", None)
        return branch is not None and branch in requirement.get("allowed_branches", [])

    if kind == "required_skill_level":
        return get_skill_level(player, requirement["skill_id"]) >= int(requirement.get("skill_level", 0))

    if kind == "any_required_skill_level":
        return any(
            get_skill_level(player, option["skill_id"]) >= int(option.get("skill_level", 0))
            for option in requirement.get("options", [])
        )

    if kind == "required_modifier_level":
        return get_modifier_level(
            player,
            requirement["skill_id"],
            requirement["modifier_name"],
        ) >= int(requirement.get("modifier_level", 0))

    if kind == "invested_attribute":
        invested = getattr(player, "invested_attributes", {}).get(requirement.get("attribute"), 0)
        return invested >= int(requirement.get("threshold", 0))

    if kind == "weapon_type":
        equipped = get_equipped_weapon_type(player)
        allowed_raw = requirement.get("allowed", [])
        if isinstance(allowed_raw, str):
            allowed_raw = [allowed_raw]
        allowed = set(allowed_raw)
        return equipped in allowed or UNIVERSAL_WEAPON_VALUE in allowed

    if kind == "equipment_type":
        armor = get_equipped_armor_type(player)
        allowed = set(requirement.get("allowed", []))
        return armor in allowed

    if kind == "weapon_or_equipment_type":
        equipped = get_equipped_weapon_type(player)
        armor = get_equipped_armor_type(player)
        allowed_weapons = set(requirement.get("allowed_weapons", []))
        allowed_equipment = set(requirement.get("allowed_equipment", []))
        return (
            UNIVERSAL_WEAPON_VALUE in allowed_weapons
            or equipped in allowed_weapons
            or armor in allowed_equipment
        )

    if kind == "learning_source":
        return has_learning_source(player, requirement.get("source", ""))

    return False


def can_learn_or_use_skill(player: Any, skill: dict[str, Any], registry: dict[str, Any]) -> bool:
    branch = skill.get("resource_branch")
    unlock = skill.get("unlock", {})

    if branch == "neutral":
        return True

    player_branch = getattr(player, "skill_branch", None)
    if not player_branch:
        return False

    allowed = skill.get("allowed_branches", [])
    if player_branch not in allowed:
        return False

    for requirement in unlock.get("requirements", []):
        if not check_skill_requirement(player, requirement, registry):
            return False

    if not is_weapon_allowed_for_skill(player, skill):
        return False

    # Для лука нужен колчан со стрелами, для арбалета — колчан с болтами.
    # Проверяем до траты духа/маны.
    if not has_required_ammo(player, skill):
        return False

    if skill.get("resource") == "spirit" and getattr(player, "spirit", 0) < skill.get("base_resource_cost", 0):
        return False

    if skill.get("resource") == "mana" and getattr(player, "mana", 0) < skill.get("base_resource_cost", 0):
        return False

    return True


def get_available_skills(player: Any, registry: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        skill
        for skill in registry.get("skills", [])
        if can_learn_or_use_skill(player, skill, registry)
    ]


def choose_branch(player: Any, branch: str) -> None:
    """Закрепляет ветвь у Распорядительного камня."""
    if branch not in ("spirit", "mana"):
        raise ValueError("branch must be 'spirit' or 'mana'")
    if getattr(player, "skill_branch", None):
        raise ValueError("skill branch already chosen")
    if not can_choose_branch_at_order_stone(player):
        raise ValueError("branch choice is not available here")
    player.skill_branch = branch
