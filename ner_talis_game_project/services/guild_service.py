"""Гильдии V2 (ТЗ «Гильдии»). Слой данных + валидация + участники.

Хранение через генерик EntityStore (data/guilds.json). Аудит и права — в
роутере (admin_community_api) через admin_operation. Склад/казна/гильдейские
задания/рейтинги — на вырост (поля заложены, но операции добавятся позже).
"""

from __future__ import annotations

from typing import Any

from services.admin_entity_store import EntityError, EntityStore

# --- Статусы жизненного цикла гильдии ---------------------------------------
STATUS_DRAFT = "draft"
STATUS_ACTIVE = "active"
STATUS_FROZEN = "frozen"
STATUS_DISBANDED = "disbanded"
STATUS_ARCHIVE = "archive"

STATUSES = (STATUS_DRAFT, STATUS_ACTIVE, STATUS_FROZEN, STATUS_DISBANDED, STATUS_ARCHIVE)
STATUS_LABELS = {
    STATUS_DRAFT: "Черновик",
    STATUS_ACTIVE: "Активна",
    STATUS_FROZEN: "Заморожена",
    STATUS_DISBANDED: "Распущена",
    STATUS_ARCHIVE: "Архив",
}
TRANSITIONS: dict[str, set[str]] = {
    STATUS_DRAFT: {STATUS_ACTIVE, STATUS_ARCHIVE},
    STATUS_ACTIVE: {STATUS_FROZEN, STATUS_DISBANDED, STATUS_ARCHIVE},
    STATUS_FROZEN: {STATUS_ACTIVE, STATUS_DISBANDED, STATUS_ARCHIVE},
    STATUS_DISBANDED: {STATUS_ARCHIVE},
    STATUS_ARCHIVE: set(),
}

GUILD_TYPES = (
    "player", "story", "npc", "raid", "trade", "craft", "order", "research",
)
GUILD_ROLES = (
    "leader", "deputy", "officer", "treasurer", "raid_leader",
    "recruiter", "member", "newbie",
)

_store = EntityStore(
    env_var="GUILDS_PATH",
    default_rel="data/guilds.json",
    statuses=STATUSES,
    transitions=TRANSITIONS,
    initial_status=STATUS_DRAFT,
)


def store() -> EntityStore:
    return _store


def _has_markup(value: str) -> bool:
    low = value.lower()
    return "<script" in low or ("<" in value and ">" in value)


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not str(data.get("name") or "").strip():
        errors.append("Не заполнено название гильдии.")
    guild_type = str(data.get("guild_type") or "").strip()
    if guild_type and guild_type not in GUILD_TYPES:
        errors.append(f"Неизвестный тип гильдии: {guild_type}.")

    min_level = _num(data.get("min_level"))
    if min_level is not None and min_level < 1:
        errors.append("Минимальный уровень вступления должен быть ≥ 1.")
    max_members = _num(data.get("max_members"))
    if max_members is not None and max_members < 1:
        errors.append("Максимум участников должен быть ≥ 1.")

    members = data.get("members")
    if members not in (None, "") and not isinstance(members, list):
        errors.append("Список участников должен быть массивом.")
    if isinstance(members, list) and max_members is not None and len(members) > max_members:
        errors.append("Участников больше, чем максимум.")
    if not str(data.get("leader") or "").strip():
        warnings.append("Не назначен лидер гильдии.")

    for key in ("name", "short_description", "description"):
        value = str(data.get(key) or "").strip()
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


# --- Операции с участниками -------------------------------------------------
def _members(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    raw = (envelope.get("data") or {}).get("members")
    return [m for m in raw if isinstance(m, dict)] if isinstance(raw, list) else []


def add_member(guild_id: str, user_id: str, role: str = "newbie", *, actor: str = "") -> dict[str, Any]:
    user_id = str(user_id or "").strip()
    if not user_id:
        raise EntityError("Не указан игрок.")
    if role not in GUILD_ROLES:
        raise EntityError(f"Неизвестная роль в гильдии: {role}.")
    envelope = _store.get(guild_id)
    if envelope is None:
        raise EntityError("Гильдия не найдена.")
    members = _members(envelope)
    if any(str(m.get("user_id")) == user_id for m in members):
        raise EntityError("Игрок уже в гильдии.")
    members.append({"user_id": user_id, "role": role})
    return _store.update(guild_id, {"members": members}, actor=actor)


def remove_member(guild_id: str, user_id: str, *, actor: str = "") -> dict[str, Any]:
    user_id = str(user_id or "").strip()
    envelope = _store.get(guild_id)
    if envelope is None:
        raise EntityError("Гильдия не найдена.")
    members = [m for m in _members(envelope) if str(m.get("user_id")) != user_id]
    return _store.update(guild_id, {"members": members}, actor=actor)


def set_member_role(guild_id: str, user_id: str, role: str, *, actor: str = "") -> dict[str, Any]:
    if role not in GUILD_ROLES:
        raise EntityError(f"Неизвестная роль в гильдии: {role}.")
    user_id = str(user_id or "").strip()
    envelope = _store.get(guild_id)
    if envelope is None:
        raise EntityError("Гильдия не найдена.")
    members = _members(envelope)
    if not any(str(m.get("user_id")) == user_id for m in members):
        raise EntityError("Игрок не состоит в гильдии.")
    for m in members:
        if str(m.get("user_id")) == user_id:
            m["role"] = role
    return _store.update(guild_id, {"members": members}, actor=actor)
