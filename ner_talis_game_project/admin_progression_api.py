"""Роутеры конструкторов прогрессии (чат-ТЗ «уровни/опыт/регистрация/расы»).

Собираются из общей фабрики create_entity_constructor_router — без дублирования.
Монтируются под /api/admin/v2/{levels,exp,registration,races}.
"""

from __future__ import annotations

from typing import Any

from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_rbac import (
    PERM_EXP_ARCHIVE, PERM_EXP_CREATE, PERM_EXP_DELETE, PERM_EXP_DISABLE,
    PERM_EXP_EDIT, PERM_EXP_PUBLISH, PERM_EXP_VALIDATE, PERM_EXP_VIEW,
    PERM_LEVEL_ARCHIVE, PERM_LEVEL_CREATE, PERM_LEVEL_DELETE, PERM_LEVEL_DISABLE,
    PERM_LEVEL_EDIT, PERM_LEVEL_PUBLISH, PERM_LEVEL_VALIDATE, PERM_LEVEL_VIEW,
    PERM_RACE_ARCHIVE, PERM_RACE_CREATE, PERM_RACE_DELETE, PERM_RACE_DISABLE,
    PERM_RACE_EDIT, PERM_RACE_PUBLISH, PERM_RACE_VALIDATE, PERM_RACE_VIEW,
    PERM_REGISTRATION_ARCHIVE, PERM_REGISTRATION_CREATE, PERM_REGISTRATION_DELETE,
    PERM_REGISTRATION_DISABLE, PERM_REGISTRATION_EDIT, PERM_REGISTRATION_PUBLISH,
    PERM_REGISTRATION_VALIDATE, PERM_REGISTRATION_VIEW,
)
from services import exp_constructor_service as exp_svc
from services import level_constructor_service as level_svc
from services import race_constructor_service as race_svc
from services import registration_constructor_service as reg_svc


def _perms(prefix_consts) -> dict[str, str]:
    return dict(zip(("view", "create", "edit", "validate", "publish", "disable", "archive", "delete"), prefix_consts))


def create_admin_levels_router(get_storage) -> Any:
    return create_entity_constructor_router(
        get_storage=get_storage, prefix="/api/admin/v2/levels", tags=["admin-levels"],
        svc=level_svc, target_type="level", name_field="title", not_found="Уровень не найден.",
        perms=_perms((PERM_LEVEL_VIEW, PERM_LEVEL_CREATE, PERM_LEVEL_EDIT, PERM_LEVEL_VALIDATE,
                      PERM_LEVEL_PUBLISH, PERM_LEVEL_DISABLE, PERM_LEVEL_ARCHIVE, PERM_LEVEL_DELETE)),
        meta_extra=lambda svc:{"entityTypes":[{"value":"rule","label":"Правило прогрессии"},{"value":"level","label":"Строка таблицы уровней"}]},
    )


def create_admin_exp_router(get_storage) -> Any:
    return create_entity_constructor_router(
        get_storage=get_storage, prefix="/api/admin/v2/exp", tags=["admin-exp"],
        svc=exp_svc, target_type="exp", name_field="name", not_found="Источник опыта не найден.",
        perms=_perms((PERM_EXP_VIEW, PERM_EXP_CREATE, PERM_EXP_EDIT, PERM_EXP_VALIDATE,
                      PERM_EXP_PUBLISH, PERM_EXP_DISABLE, PERM_EXP_ARCHIVE, PERM_EXP_DELETE)),
        meta_extra=lambda svc: {"sourceTypes": [{"value": s, "label": svc.SOURCE_TYPE_LABELS.get(s, s)} for s in svc.SOURCE_TYPES]},
    )


def create_admin_registration_router(get_storage) -> Any:
    return create_entity_constructor_router(
        get_storage=get_storage, prefix="/api/admin/v2/registration", tags=["admin-registration"],
        svc=reg_svc, target_type="registration", name_field="label", not_found="Шаг регистрации не найден.",
        perms=_perms((PERM_REGISTRATION_VIEW, PERM_REGISTRATION_CREATE, PERM_REGISTRATION_EDIT, PERM_REGISTRATION_VALIDATE,
                      PERM_REGISTRATION_PUBLISH, PERM_REGISTRATION_DISABLE, PERM_REGISTRATION_ARCHIVE, PERM_REGISTRATION_DELETE)),
        meta_extra=lambda svc: {"stepTypes": [{"value": s, "label": svc.STEP_TYPE_LABELS.get(s, s)} for s in svc.STEP_TYPES], "entityTypes": [{"value":"scenario","label":"Сценарий регистрации"},{"value":"step","label":"Отдельный шаг"}]},
    )


def create_admin_races_router(get_storage) -> Any:
    return create_entity_constructor_router(
        get_storage=get_storage, prefix="/api/admin/v2/races", tags=["admin-races"],
        svc=race_svc, target_type="race", name_field="race_name", not_found="Раса не найдена.",
        perms=_perms((PERM_RACE_VIEW, PERM_RACE_CREATE, PERM_RACE_EDIT, PERM_RACE_VALIDATE,
                      PERM_RACE_PUBLISH, PERM_RACE_DISABLE, PERM_RACE_ARCHIVE, PERM_RACE_DELETE)),
        meta_extra=lambda svc: {"stats": [{"value": s, "label": svc.STAT_LABELS.get(s, s)} for s in svc.STATS], "bonusTypes": list(svc.BONUS_TYPES)},
        import_fn_name="import_races",
    )
