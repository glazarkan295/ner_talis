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
    "hp",
    "spirit",
    "mana",
    "concentration",
    "branch",
    "storage",
    "equipment",
    "skills",
    "starter_pack_applied",
    "active_effects",
    "active_sets",
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


def ensure_starter_pack(player: dict[str, Any]) -> bool:
    if player.get("starter_pack_applied"):
        return False

    changed = False
    if not isinstance(player.get("equipment"), dict) or not player.get("equipment"):
        player["equipment"] = get_starter_equipment()
        changed = True

    skills = player.get("skills")
    active_skills = skills.get("active") if isinstance(skills, dict) else None
    if not isinstance(skills, dict) or not isinstance(active_skills, list) or not active_skills:
        player["skills"] = get_starter_skills()
        changed = True

    player["starter_pack_applied"] = True
    return changed or True


def sync_starter_skills(player: dict[str, Any]) -> bool:
    """Update existing starter skills to the current level-0 definition."""
    skills = player.get("skills")
    if not isinstance(skills, dict):
        return False

    active = skills.get("active")
    if not isinstance(active, list):
        return False

    starter_by_id = {skill["id"]: skill for skill in get_starter_skills().get("active", [])}
    changed = False
    for index, skill in enumerate(active):
        if not isinstance(skill, dict):
            continue
        starter = starter_by_id.get(skill.get("id"))
        if not starter:
            continue
        merged = deepcopy(starter)
        for key, value in skill.items():
            if key not in merged:
                merged[key] = value
        if merged != skill:
            active[index] = merged
            changed = True
    return changed


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

    original_normalize = storage_class._normalize_player
    original_row_to_player = storage_class._row_to_player
    original_upsert = storage_class._upsert_player

    def _normalize_player(self: Any, player: dict[str, Any]) -> dict[str, Any]:
        normalized = original_normalize(self, player)
        ensure_starter_pack(normalized)
        sync_starter_skills(normalized)
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
        sync_starter_skills(player)
        player["extra"] = build_extra_payload(player)
        return player

    def _upsert_player(self: Any, player: dict[str, Any]) -> dict[str, Any]:
        patched_player = dict(player)
        ensure_starter_pack(patched_player)
        sync_starter_skills(patched_player)
        patched_player["extra"] = build_extra_payload(patched_player)
        return original_upsert(self, patched_player)

    storage_class._normalize_player = _normalize_player
    storage_class._row_to_player = _row_to_player
    storage_class._upsert_player = _upsert_player
    storage_class._ensure_starter_pack = staticmethod(ensure_starter_pack)
    storage_class._sync_starter_skills = staticmethod(sync_starter_skills)
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
