"""FastAPI routers for the expanded craft constructors (ТЗ 13 §5).

Two EntityStore constructors built on the shared factory:
- professions  → /api/admin/v2/professions  (profession.*)
- workshops    → /api/admin/v2/workshops    (workshop.*)

CRUD/lifecycle/versioning come from create_entity_constructor_router; meta_extra
supplies the type dictionaries for the SPA.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from services import profession_constructor_service as professions
from services import workshop_constructor_service as workshops
from services import craft_material_group_service as material_groups
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_rbac import (
    PERM_PROFESSION_ARCHIVE, PERM_PROFESSION_CREATE, PERM_PROFESSION_DELETE,
    PERM_PROFESSION_DISABLE, PERM_PROFESSION_EDIT, PERM_PROFESSION_PUBLISH,
    PERM_PROFESSION_VALIDATE, PERM_PROFESSION_VIEW,
    PERM_WORKSHOP_ARCHIVE, PERM_WORKSHOP_CREATE, PERM_WORKSHOP_DELETE,
    PERM_WORKSHOP_DISABLE, PERM_WORKSHOP_EDIT, PERM_WORKSHOP_PUBLISH,
    PERM_WORKSHOP_VALIDATE, PERM_WORKSHOP_VIEW,
    PERM_RECIPE_ARCHIVE, PERM_RECIPE_CREATE, PERM_RECIPE_DELETE, PERM_RECIPE_DISABLE,
    PERM_RECIPE_EDIT, PERM_RECIPE_PUBLISH, PERM_RECIPE_VALIDATE, PERM_RECIPE_VIEW,
)

_PROF_PERMS = {
    "view": PERM_PROFESSION_VIEW, "create": PERM_PROFESSION_CREATE, "edit": PERM_PROFESSION_EDIT,
    "validate": PERM_PROFESSION_VALIDATE, "publish": PERM_PROFESSION_PUBLISH,
    "disable": PERM_PROFESSION_DISABLE, "archive": PERM_PROFESSION_ARCHIVE,
    "delete": PERM_PROFESSION_DELETE,
}
_WS_PERMS = {
    "view": PERM_WORKSHOP_VIEW, "create": PERM_WORKSHOP_CREATE, "edit": PERM_WORKSHOP_EDIT,
    "validate": PERM_WORKSHOP_VALIDATE, "publish": PERM_WORKSHOP_PUBLISH,
    "disable": PERM_WORKSHOP_DISABLE, "archive": PERM_WORKSHOP_ARCHIVE,
    "delete": PERM_WORKSHOP_DELETE,
}


def create_admin_profession_router(get_storage) -> APIRouter:
    return create_entity_constructor_router(
        get_storage=get_storage,
        prefix="/api/admin/v2/professions",
        tags=["admin-professions"],
        svc=professions,
        perms=_PROF_PERMS,
        target_type="profession",
        name_field="name",
        not_found="Профессия не найдена.",
        meta_extra=lambda _svc: {
            "professionTypes": [{"value": p, "label": professions.PROFESSION_TYPE_LABELS.get(p, p)}
                                for p in professions.PROFESSION_TYPES],
        },
    )


def create_admin_workshop_router(get_storage) -> APIRouter:
    return create_entity_constructor_router(
        get_storage=get_storage,
        prefix="/api/admin/v2/workshops",
        tags=["admin-workshops"],
        svc=workshops,
        perms=_WS_PERMS,
        target_type="workshop",
        name_field="name",
        not_found="Мастерская не найдена.",
        meta_extra=lambda _svc: {
            "workshopTypes": [{"value": w, "label": workshops.WORKSHOP_TYPE_LABELS.get(w, w)}
                              for w in workshops.WORKSHOP_TYPES],
        },
    )


def create_admin_material_group_router(get_storage) -> APIRouter:
    return create_entity_constructor_router(
        get_storage=get_storage,
        prefix="/api/admin/v2/craft-material-groups",
        tags=["admin-craft-material-groups"],
        svc=material_groups,
        perms={
            "view": PERM_RECIPE_VIEW, "create": PERM_RECIPE_CREATE, "edit": PERM_RECIPE_EDIT,
            "validate": PERM_RECIPE_VALIDATE, "publish": PERM_RECIPE_PUBLISH,
            "disable": PERM_RECIPE_DISABLE, "archive": PERM_RECIPE_ARCHIVE, "delete": PERM_RECIPE_DELETE,
        },
        target_type="craft_material_group",
        name_field="name",
        not_found="Группа материалов не найдена.",
    )
