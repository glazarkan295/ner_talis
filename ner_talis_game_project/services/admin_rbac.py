"""RBAC для админ-панели V2 — роли, права и их разрешение.

Модель доступа (гибрид):

* **ENV-bootstrap** — каждый, кто указан в ``TELEGRAM_ADMIN_USER_IDS`` /
  ``VK_ADMIN_USER_IDS`` (текущий механизм доступа), по умолчанию получает роль
  ``owner``, чтобы при включении RBAC никто не потерял доступ.
* **Override в хранилище** — owner может переопределить роль любого админа; такие
  переопределения хранятся персистентно (файл ``data/admin_roles.json`` с
  блокировкой, как у портового рынка/курьера) и имеют приоритет над ENV.

Право проверяется на КАЖДОМ изменяющем admin-эндпоинте, а не только факт
наличия сессии. ``owner`` имеет все права (sentinel ``*``).
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

try:  # POSIX-блокировка (на Windows отсутствует)
    import fcntl
except Exception:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

from project_paths import project_path, resolve_project_path
from services.admin_access import is_configured_admin_user

# --- Роли -------------------------------------------------------------------
OWNER = "owner"
ADMIN = "admin"
SUPPORT = "support"
MODERATOR = "moderator"
CONTENT = "content"
ECONOMY = "economy"
READ_ONLY = "read_only"

ROLES = (OWNER, ADMIN, SUPPORT, MODERATOR, CONTENT, ECONOMY, READ_ONLY)
DEFAULT_ROLE = READ_ONLY

ROLE_LABELS = {
    OWNER: "Владелец",
    ADMIN: "Администратор",
    SUPPORT: "Поддержка",
    MODERATOR: "Модератор",
    CONTENT: "Контент",
    ECONOMY: "Экономика",
    READ_ONLY: "Только чтение",
}

# --- Права ------------------------------------------------------------------
# Просмотр
PERM_PLAYERS_VIEW = "players.view"
PERM_CATALOG_VIEW = "catalog.view"
PERM_ECONOMY_VIEW = "economy.view"
PERM_PROMOS_VIEW = "promos.view"
PERM_MODERATION_VIEW = "moderation.view"
PERM_AUDIT_VIEW = "audit.view"
PERM_SYSTEM_VIEW = "system.view"
PERM_BACKUP_VIEW = "backup.view"
# Игроки / поддержка
PERM_PLAYERS_DELETE = "players.delete"
PERM_PLAYERS_RESET = "players.reset"
PERM_PLAYERS_UNSTUCK = "players.unstuck"
PERM_PLAYERS_MESSAGE = "players.message"
PERM_BACKUP_RESTORE = "backup.restore"
# Награды / экономика игрока
PERM_REWARDS_GRANT = "rewards.grant"
PERM_REWARDS_REMOVE = "rewards.remove"
PERM_REWARDS_BULK = "rewards.bulk_grant"
PERM_CURRENCY_CHANGE = "currency.change"
PERM_INVENTORY_EDIT = "inventory.edit"
# Модерация
PERM_MOD_WARN = "moderation.warn"
PERM_MOD_MUTE = "moderation.mute"
PERM_MOD_BAN = "moderation.ban"
PERM_FINES_MANAGE = "fines.manage"
# Экономика мира
PERM_ECONOMY_MANAGE = "economy.manage"
# Контент
PERM_CONTENT_EDIT = "content.edit"
PERM_ASSETS_MANAGE = "assets.manage"
# Промокоды / рассылки
PERM_PROMOS_MANAGE = "promos.manage"
PERM_BROADCAST_SEND = "broadcast.send"
# Система
PERM_SYSTEM_MANAGE = "system.manage"
PERM_ROLES_MANAGE = "roles.manage"

ALL_PERMISSIONS = (
    PERM_PLAYERS_VIEW, PERM_CATALOG_VIEW, PERM_ECONOMY_VIEW, PERM_PROMOS_VIEW,
    PERM_MODERATION_VIEW, PERM_AUDIT_VIEW, PERM_SYSTEM_VIEW, PERM_BACKUP_VIEW,
    PERM_PLAYERS_DELETE, PERM_PLAYERS_RESET, PERM_PLAYERS_UNSTUCK,
    PERM_PLAYERS_MESSAGE, PERM_BACKUP_RESTORE,
    PERM_REWARDS_GRANT, PERM_REWARDS_REMOVE, PERM_REWARDS_BULK,
    PERM_CURRENCY_CHANGE, PERM_INVENTORY_EDIT,
    PERM_MOD_WARN, PERM_MOD_MUTE, PERM_MOD_BAN, PERM_FINES_MANAGE,
    PERM_ECONOMY_MANAGE, PERM_CONTENT_EDIT, PERM_ASSETS_MANAGE,
    PERM_PROMOS_MANAGE, PERM_BROADCAST_SEND,
    PERM_SYSTEM_MANAGE, PERM_ROLES_MANAGE,
)

# Опасные действия — требуют двойного подтверждения на фронте и помечаются в
# аудите. Используется и эндпоинтами, и вьювером аудита (фильтр «опасные»).
DANGEROUS_ACTIONS = frozenset({
    "player.delete",
    "player.reset",
    "backup.restore",
    "rewards.bulk_grant",
    "rewards.bulk_remove",
    "currency.large_change",
    "promo.delete",
    "asset.image_change",
    "system.maintenance_on",
    "system.feature_flag",
    "roles.change",
})

# owner → все права (sentinel). Остальные роли — явные множества.
ROLE_PERMISSIONS: dict[str, set[str]] = {
    OWNER: {"*"},
    ADMIN: set(p for p in ALL_PERMISSIONS if p != PERM_ROLES_MANAGE),
    SUPPORT: {
        PERM_PLAYERS_VIEW, PERM_PLAYERS_UNSTUCK, PERM_PLAYERS_MESSAGE,
        PERM_REWARDS_GRANT, PERM_BACKUP_VIEW, PERM_AUDIT_VIEW,
    },
    MODERATOR: {
        PERM_PLAYERS_VIEW, PERM_MODERATION_VIEW,
        PERM_MOD_WARN, PERM_MOD_MUTE,
    },
    CONTENT: {
        PERM_CATALOG_VIEW, PERM_CONTENT_EDIT, PERM_ASSETS_MANAGE,
    },
    ECONOMY: {
        PERM_ECONOMY_VIEW, PERM_ECONOMY_MANAGE, PERM_CATALOG_VIEW,
        PERM_PROMOS_VIEW, PERM_AUDIT_VIEW,
    },
    READ_ONLY: {
        PERM_PLAYERS_VIEW, PERM_CATALOG_VIEW, PERM_ECONOMY_VIEW,
        PERM_PROMOS_VIEW, PERM_MODERATION_VIEW, PERM_AUDIT_VIEW,
        PERM_SYSTEM_VIEW, PERM_BACKUP_VIEW,
    },
}


def normalize_role(role: Any) -> str:
    value = str(role or "").strip().casefold()
    return value if value in ROLES else DEFAULT_ROLE


def permissions_for(role: str) -> set[str]:
    role = normalize_role(role)
    perms = ROLE_PERMISSIONS.get(role, set())
    if "*" in perms:
        return set(ALL_PERMISSIONS)
    return set(perms)


def has_permission(role: str, permission: str) -> bool:
    role = normalize_role(role)
    perms = ROLE_PERMISSIONS.get(role, set())
    return "*" in perms or permission in perms


# --- Хранилище override'ов ролей (файл с блокировкой) -----------------------
_ROLES_LOCK = threading.Lock()


def roles_path() -> Path:
    override = os.getenv("ADMIN_ROLES_PATH")
    if override:
        return resolve_project_path(override)
    return project_path("data", "admin_roles.json")


def _load_roles() -> dict[str, str]:
    path = roles_path()
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(data, dict):
        data = data.get("roles", data)
    if not isinstance(data, dict):
        return {}
    return {str(key): normalize_role(value) for key, value in data.items() if value}


def _save_roles(roles: dict[str, str]) -> None:
    path = roles_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as file:
        json.dump({"roles": roles}, file, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


@contextmanager
def _roles_file_lock() -> Iterator[None]:
    if fcntl is None:
        yield
        return
    path = roles_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def identity_key(platform: Any, admin_user_id: Any) -> str:
    return f"{str(platform or '').strip().casefold()}:{str(admin_user_id or '').strip()}"


def get_role_overrides() -> dict[str, str]:
    with _ROLES_LOCK, _roles_file_lock():
        return _load_roles()


def set_role_override(platform: Any, admin_user_id: Any, role: str) -> str:
    role = normalize_role(role)
    key = identity_key(platform, admin_user_id)
    with _ROLES_LOCK, _roles_file_lock():
        roles = _load_roles()
        roles[key] = role
        _save_roles(roles)
    return role


def remove_role_override(platform: Any, admin_user_id: Any) -> bool:
    key = identity_key(platform, admin_user_id)
    with _ROLES_LOCK, _roles_file_lock():
        roles = _load_roles()
        if key not in roles:
            return False
        roles.pop(key, None)
        _save_roles(roles)
    return True


def resolve_admin_role(platform: Any, admin_user_id: Any) -> str:
    """Роль админа: override из хранилища → ENV-bootstrap (owner) → default."""
    overrides = get_role_overrides()
    key = identity_key(platform, admin_user_id)
    if key in overrides:
        return overrides[key]
    if is_configured_admin_user(platform, admin_user_id):
        return OWNER
    return DEFAULT_ROLE


def role_for_session(session: dict[str, Any] | None) -> str:
    if not isinstance(session, dict):
        return DEFAULT_ROLE
    return resolve_admin_role(session.get("platform"), session.get("admin_user_id"))


def session_has_permission(session: dict[str, Any] | None, permission: str) -> bool:
    return has_permission(role_for_session(session), permission)


def require_permission(session: dict[str, Any] | None, permission: str) -> str:
    """Возвращает роль, если право есть; иначе бросает PermissionError."""
    role = role_for_session(session)
    if not has_permission(role, permission):
        raise PermissionError(
            f"Недостаточно прав: требуется «{permission}» (ваша роль: {ROLE_LABELS.get(role, role)})."
        )
    return role
