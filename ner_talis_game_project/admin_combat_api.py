"""FastAPI router for the combat-settings constructor (ТЗ 20 §1–§4, §10).

CRUD/lifecycle/versioning via the shared factory. Guarded by combat.*.
Mounted under ``/api/admin/v2/combat``. Combat runtime reads these profiles —
authoring layer only.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from services import combat_constructor_service as svc
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_rbac import (
    PERM_COMBAT_ARCHIVE, PERM_COMBAT_CREATE, PERM_COMBAT_DELETE, PERM_COMBAT_DISABLE,
    PERM_COMBAT_EDIT, PERM_COMBAT_PUBLISH, PERM_COMBAT_VALIDATE, PERM_COMBAT_VIEW,
)

_PERMS = {
    "view": PERM_COMBAT_VIEW, "create": PERM_COMBAT_CREATE, "edit": PERM_COMBAT_EDIT,
    "validate": PERM_COMBAT_VALIDATE, "publish": PERM_COMBAT_PUBLISH,
    "disable": PERM_COMBAT_DISABLE, "archive": PERM_COMBAT_ARCHIVE,
    "delete": PERM_COMBAT_DELETE,
}


def _meta_extra(_svc: Any) -> dict[str, Any]:
    return {
        "scopes": [{"value": s, "label": svc.SCOPE_LABELS.get(s, s)} for s in svc.SCOPES],
        "timeoutActions": [{"value": a, "label": svc.TIMEOUT_ACTION_LABELS.get(a, a)} for a in svc.TIMEOUT_ACTIONS],
        "allyOrderTypes": list(svc.ALLY_ORDER_TYPES),
        "playerOrderTypes": list(svc.PLAYER_ORDER_TYPES),
        "mixedOrderTypes": list(svc.MIXED_ORDER_TYPES),
        "enemyOrderTypes": list(svc.ENEMY_ORDER_TYPES),
        "enemyTargetRules": list(svc.ENEMY_TARGET_RULES),
        "defaultTurnSeconds": svc.DEFAULT_TURN_SECONDS,
    }


def create_admin_combat_router(get_storage) -> APIRouter:
    return create_entity_constructor_router(
        get_storage=get_storage,
        prefix="/api/admin/v2/combat",
        tags=["admin-combat"],
        svc=svc,
        perms=_PERMS,
        target_type="combat",
        name_field="name",
        not_found="Профиль боя не найден.",
        meta_extra=_meta_extra,
    )
