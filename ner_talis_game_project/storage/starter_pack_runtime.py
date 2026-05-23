"""Runtime starter-pack preservation for PostgreSQL storage.

PostgresStorage stores only a limited set of profile fields as table columns.
Everything else must be packed into the `extra` JSONB column. Without this,
starter equipment and starter skills can disappear after saving/loading through
PostgreSQL.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from game_data.starter_items import get_starter_equipment
from game_data.starter_skills import get_starter_skills

STARTER_EXTRA_FIELDS = {
    "main_platform",
    "linked_accounts",
    "location_id",
    "bonus_max_energy",
    "in_battle",
    "is_dead",
    "invested_stats",
    "stat_bonuses",
    "free_stat_points",
    "free_skill_points",
    "experience_to_next",
    "total_experience",
    "hp",
    "spirit",
    "mana",
    "branch",
    "skill_branch",
    "branch_choice_hint_sent",
    "branch_chosen_at",
    "branch_choice_place",
    "has_identification_amulet",
    "unlocked_skill_sources",
    "skill_equip_capacity",
    "storage",
    "equipment",
    "skills",
    "starter_pack_applied",
    "active_effects",
    "active_sets",
    "active_timer",
    "known_recipes",
    "alchemy_level",
    "alchemy_experience",
    "unlocked_alchemy_recipes",
    "alchemy_known_failures",
    "owned_special_recipes",
    "achievements",
    "rating",
    "pve_kills",
    "pvp_kills",
    "soul_particles_absorbed",
    "admin_reset_at",
}

POSTGRES_COLUMN_FIELDS = {
    "game_id",
    "id",
    "public_id",
    "name",
    "race_id",
    "race_name",
    "level",
    "experience",
    "money",
    "debt",
    "energy",
    "max_energy",
    "current_city",
    "current_zone",
    "stats",
    "inventory",
    "crafting_levels",
    "housing",
    "extra",
    "created_at",
    "updated_at",
}

STARTER_SKILL_IDS = {skill["id"]: skill for skill in get_starter_skills()["active"]}


def sync_starter_skill_definitions(player: dict[str, Any]) -> bool:
    """Update old starter skills to the current non-upgradeable definition."""
    skills = player.get("skills")
    if not isinstance(skills, dict):
        return False

    active_skills = skills.get("active")
    if not isinstance(active_skills, list):
        return False

    changed = False
    for index, skill in enumerate(active_skills):
        if not isinstance(skill, dict):
            continue
        skill_id = skill.get("id")
        template = STARTER_SKILL_IDS.get(skill_id)
        if not template:
            continue

        updated = deepcopy(skill)
        for key, value in template.items():
            if updated.get(key) != value:
                updated[key] = deepcopy(value)
                changed = True
        active_skills[index] = updated

    return changed


def ensure_starter_pack(player: dict[str, Any]) -> bool:
    """Ensure a profile has starter gear and current starter skills exactly once."""
    changed = False

    branch_changed = False
    if "skill_branch" not in player:
        player["skill_branch"] = None
        branch_changed = True
    if "branch_choice_hint_sent" not in player:
        player["branch_choice_hint_sent"] = False
        branch_changed = True
    if "has_identification_amulet" not in player:
        player["has_identification_amulet"] = True
        branch_changed = True
    if "unlocked_skill_sources" not in player:
        player["unlocked_skill_sources"] = []
        branch_changed = True

    if player.get("starter_pack_applied"):
        return sync_starter_skill_definitions(player) or branch_changed

    if not isinstance(player.get("equipment"), dict) or not player.get("equipment"):
        player["equipment"] = get_starter_equipment()
        changed = True

    skills = player.get("skills")
    active_skills = skills.get("active") if isinstance(skills, dict) else None
    if not isinstance(skills, dict) or not isinstance(active_skills, list) or not active_skills:
        player["skills"] = get_starter_skills()
        changed = True
    else:
        changed = sync_starter_skill_definitions(player) or changed

    player["starter_pack_applied"] = True
    return True


def build_extra_payload(player: dict[str, Any]) -> dict[str, Any]:
    raw_extra = player.get("extra")
    extra = dict(raw_extra) if isinstance(raw_extra, dict) else {}

    for key, value in player.items():
        if key.startswith("_"):
            continue
        if key in STARTER_EXTRA_FIELDS or key not in POSTGRES_COLUMN_FIELDS:
            extra[key] = deepcopy(value)

    return extra


def patch_postgres_starter_pack(storage_class: type[Any]) -> type[Any]:
    if getattr(storage_class, "_starter_pack_runtime_patched", False):
        return storage_class

    if getattr(storage_class, "_starter_pack_native", False):
        storage_class._ensure_starter_pack = staticmethod(ensure_starter_pack)
        storage_class._build_extra_payload = staticmethod(build_extra_payload)
        storage_class.COLUMN_FIELDS = POSTGRES_COLUMN_FIELDS
        storage_class.DEFAULT_EXTRA_FIELDS = STARTER_EXTRA_FIELDS
        storage_class._starter_pack_runtime_patched = True
        return storage_class

    original_normalize = storage_class._normalize_player
    original_row_to_player = storage_class._row_to_player
    original_upsert = storage_class._upsert_player

    def _normalize_player(self: Any, player: dict[str, Any]) -> dict[str, Any]:
        normalized = original_normalize(self, player)
        ensure_starter_pack(normalized)
        normalized["extra"] = build_extra_payload(normalized)
        return normalized

    def _row_to_player(self: Any, row: Any) -> dict[str, Any] | None:
        player = original_row_to_player(self, row)
        if player is None:
            return None
        extra = player.get("extra")
        if isinstance(extra, dict):
            for key, value in extra.items():
                player.setdefault(key, value)
        ensure_starter_pack(player)
        player["extra"] = build_extra_payload(player)
        return player

    def _upsert_player(self: Any, player: dict[str, Any]) -> dict[str, Any]:
        patched_player = dict(player)
        ensure_starter_pack(patched_player)
        patched_player["extra"] = build_extra_payload(patched_player)
        return original_upsert(self, patched_player)

    storage_class._normalize_player = _normalize_player
    storage_class._row_to_player = _row_to_player
    storage_class._upsert_player = _upsert_player
    storage_class._ensure_starter_pack = staticmethod(ensure_starter_pack)
    storage_class._build_extra_payload = staticmethod(build_extra_payload)
    storage_class.COLUMN_FIELDS = POSTGRES_COLUMN_FIELDS
    storage_class.DEFAULT_EXTRA_FIELDS = STARTER_EXTRA_FIELDS
    storage_class._starter_pack_runtime_patched = True
    return storage_class


def patch_known_starter_pack_storage_classes() -> None:
    try:
        from storage.postgres_storage import PostgresStorage
    except Exception:
        return

    patch_postgres_starter_pack(PostgresStorage)
