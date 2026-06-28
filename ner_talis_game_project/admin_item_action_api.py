"""FastAPI routers for item-action craft constructors (ТЗ 13 §5.10–§5.11):
upgrade / enchant / disassemble. Built on the shared factory; reuse recipe.*
permissions (these are craft actions managed by the same roles).
"""

from __future__ import annotations

from fastapi import APIRouter

from services import disassemble_constructor_service as disassemble
from services import enchant_constructor_service as enchant
from services import upgrade_constructor_service as upgrade
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_rbac import (
    PERM_RECIPE_ARCHIVE, PERM_RECIPE_CREATE, PERM_RECIPE_DELETE, PERM_RECIPE_DISABLE,
    PERM_RECIPE_EDIT, PERM_RECIPE_PUBLISH, PERM_RECIPE_VALIDATE, PERM_RECIPE_VIEW,
)

_PERMS = {
    "view": PERM_RECIPE_VIEW, "create": PERM_RECIPE_CREATE, "edit": PERM_RECIPE_EDIT,
    "validate": PERM_RECIPE_VALIDATE, "publish": PERM_RECIPE_PUBLISH,
    "disable": PERM_RECIPE_DISABLE, "archive": PERM_RECIPE_ARCHIVE, "delete": PERM_RECIPE_DELETE,
}


def create_admin_upgrade_router(get_storage) -> APIRouter:
    return create_entity_constructor_router(
        get_storage=get_storage, prefix="/api/admin/v2/upgrades", tags=["admin-upgrades"],
        svc=upgrade, perms=_PERMS, target_type="item_upgrade", name_field="name",
        not_found="Правило улучшения не найдено.",
        meta_extra=lambda _s: {"upgradeTypes": [{"value": t, "label": upgrade.UPGRADE_TYPE_LABELS.get(t, t)}
                                                for t in upgrade.UPGRADE_TYPES]},
    )


def create_admin_enchant_router(get_storage) -> APIRouter:
    return create_entity_constructor_router(
        get_storage=get_storage, prefix="/api/admin/v2/enchants", tags=["admin-enchants"],
        svc=enchant, perms=_PERMS, target_type="item_enchant", name_field="name",
        not_found="Зачарование не найдено.",
    )


def create_admin_disassemble_router(get_storage) -> APIRouter:
    return create_entity_constructor_router(
        get_storage=get_storage, prefix="/api/admin/v2/disassembles", tags=["admin-disassembles"],
        svc=disassemble, perms=_PERMS, target_type="item_disassemble", name_field="name",
        not_found="Правило разборки не найдено.",
    )
