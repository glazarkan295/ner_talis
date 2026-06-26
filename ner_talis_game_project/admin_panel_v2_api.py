"""FastAPI router for Admin Panel V2 (RBAC-aware, audited).

Phase P0: identity/permissions (`/me`), audit viewer (`/audit`) and role
management (`/roles`). Runs in parallel with the V1 router under
``/api/admin/v2`` — the existing panel is untouched. Every mutating endpoint
checks a permission via admin_rbac and records an admin_operation in the audit.
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_audit import read_admin_audit_records
from services.admin_operation import (
    record_admin_operation,
    run_admin_operation,
)
from services.admin_panel_service import (
    admin_player_detail,
    create_admin_player_view_token,
    deliver_rewards_to_player,
    list_admin_players,
    player_chat_last_24h,
    player_logs_last_24h,
    require_admin_session,
)
from services.admin_player_service import delete_player_profile, reset_player_progress
from services.admin_rbac import (
    ALL_PERMISSIONS,
    DANGEROUS_ACTIONS,
    OWNER,
    PERM_AUDIT_VIEW,
    PERM_FINES_MANAGE,
    PERM_INVENTORY_EDIT,
    PERM_PLAYERS_DELETE,
    PERM_PLAYERS_MESSAGE,
    PERM_PLAYERS_RESET,
    PERM_PLAYERS_UNSTUCK,
    PERM_PLAYERS_VIEW,
    PERM_REWARDS_GRANT,
    PERM_ROLES_MANAGE,
    PERM_SYSTEM_MANAGE,
    PERM_SYSTEM_VIEW,
    ROLE_LABELS,
    ROLES,
    get_role_overrides,
    identity_key,
    normalize_role,
    permissions_for,
    remove_role_override,
    require_permission,
    resolve_admin_role,
    role_for_session,
    set_role_override,
)


class RoleAssignRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    platform: str
    admin_user_id: str
    role: str
    reason: str = ""


class SessionRevokeRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    id: str = Field(min_length=4)
    reason: str = ""


class PlayerRewardItem(BaseModel):
    item_id: str
    amount: int = Field(gt=0)


class PlayerRewardRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    rewards: list[PlayerRewardItem]
    reason: str = ""


class PlayerMessageRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    text: str = Field(min_length=1)
    reason: str = ""


class PlayerActionRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    reason: str = ""


class PlayerDeleteRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    confirm: str = ""
    reason: str = ""


def _session_token_id(token: Any) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()[:16]


def _player_snapshot(detail: dict[str, Any] | None) -> dict[str, Any]:
    """Лёгкий слепок ключевых полей игрока для before/after в аудите."""
    if not isinstance(detail, dict):
        return {}
    return {
        "level": detail.get("level"),
        "experience": detail.get("experience"),
        "money": detail.get("money"),
        "location": detail.get("location"),
    }


def _bearer_token(request: Request | None) -> str:
    if request is None:
        return ""
    authorization = str(request.headers.get("authorization") or "").strip()
    if not authorization:
        return ""
    scheme, _, value = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not value.strip():
        return ""
    return value.strip()


def _session(storage: Any, request: Request | None, token: str | None) -> dict[str, Any]:
    effective_token = _bearer_token(request) or str(token or "").strip()
    if not effective_token:
        raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
    try:
        return require_admin_session(storage, effective_token)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _require(session: dict[str, Any], permission: str) -> str:
    try:
        return require_permission(session, permission)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _permission_catalog() -> dict[str, list[str]]:
    return {role: sorted(permissions_for(role)) for role in ROLES}


def create_admin_panel_v2_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2", tags=["admin-panel-v2"])

    @router.get("/me")
    def get_me(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, token)
        role = role_for_session(session)
        return {
            "ok": True,
            "admin_user_id": str(session.get("admin_user_id") or ""),
            "platform": session.get("platform"),
            "role": role,
            "roleLabel": ROLE_LABELS.get(role, role),
            "isOwner": role == OWNER,
            "permissions": sorted(permissions_for(role)),
            "sessionExpiresAt": session.get("expires_at"),
        }

    @router.get("/audit")
    def get_audit(
        request: Request,
        token: str | None = Query(default=None, min_length=16),
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
        since: str | None = None,
        until: str | None = None,
        admin_user_id: str | None = None,
        role: str | None = None,
        action: str | None = None,
        action_prefix: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        dangerous_only: bool = False,
        errors_only: bool = False,
    ) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, token)
        _require(session, PERM_AUDIT_VIEW)
        records = read_admin_audit_records(
            limit=limit,
            offset=offset,
            since=since,
            until=until,
            admin_user_id=admin_user_id,
            role=role,
            action=action,
            action_prefix=action_prefix,
            target_type=target_type,
            target_id=target_id,
            dangerous_actions=DANGEROUS_ACTIONS,
            dangerous_only=dangerous_only,
            errors_only=errors_only,
        )
        return {"ok": True, "records": records, "limit": limit, "offset": offset}

    @router.get("/roles")
    def get_roles(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, token)
        _require(session, PERM_ROLES_MANAGE)
        overrides = get_role_overrides()
        return {
            "ok": True,
            "roles": [{"role": r, "label": ROLE_LABELS.get(r, r)} for r in ROLES],
            "permissions": list(ALL_PERMISSIONS),
            "matrix": _permission_catalog(),
            "overrides": [{"key": key, "role": role} for key, role in sorted(overrides.items())],
            "dangerousActions": sorted(DANGEROUS_ACTIONS),
        }

    @router.post("/roles")
    def assign_role(payload: RoleAssignRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, payload.token)
        actor_role = _require(session, PERM_ROLES_MANAGE)
        new_role = normalize_role(payload.role)
        if str(payload.role).strip().casefold() not in ROLES:
            raise HTTPException(status_code=400, detail="Неизвестная роль.")
        target_key = identity_key(payload.platform, payload.admin_user_id)
        actor_key = identity_key(session.get("platform"), session.get("admin_user_id"))
        # Защита от самоблокировки: owner не может понизить сам себя.
        if target_key == actor_key and actor_role == OWNER and new_role != OWNER:
            raise HTTPException(
                status_code=400,
                detail="Нельзя понизить собственную роль owner (защита от потери доступа).",
            )
        before = resolve_admin_role(payload.platform, payload.admin_user_id)
        set_role_override(payload.platform, payload.admin_user_id, new_role)
        record_admin_operation(
            session=session,
            action="roles.change",
            target_type="admin",
            target_id=target_key,
            target_name=str(payload.admin_user_id),
            before={"role": before},
            after={"role": new_role},
            reason=payload.reason,
        )
        return {"ok": True, "key": target_key, "role": new_role}

    @router.delete("/roles")
    def clear_role(
        request: Request,
        platform: str = Query(...),
        admin_user_id: str = Query(...),
        token: str | None = Query(default=None, min_length=16),
    ) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, token)
        _require(session, PERM_ROLES_MANAGE)
        target_key = identity_key(platform, admin_user_id)
        before = resolve_admin_role(platform, admin_user_id)
        removed = remove_role_override(platform, admin_user_id)
        after = resolve_admin_role(platform, admin_user_id)
        record_admin_operation(
            session=session,
            action="roles.change",
            target_type="admin",
            target_id=target_key,
            target_name=str(admin_user_id),
            before={"role": before},
            after={"role": after, "override_removed": removed},
            reason="reset role override",
        )
        return {"ok": True, "key": target_key, "removed": removed, "role": after}

    @router.get("/sessions")
    def get_sessions(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, token)
        _require(session, PERM_SYSTEM_VIEW)
        current = _bearer_token(request) or str(token or "")
        raw = storage.list_admin_panel_sessions() if hasattr(storage, "list_admin_panel_sessions") else []
        items: list[dict[str, Any]] = []
        for sess in raw:
            tok = sess.get("token") or ""
            items.append({
                "id": _session_token_id(tok),
                "platform": sess.get("platform"),
                "adminUserId": str(sess.get("admin_user_id") or ""),
                "scope": sess.get("scope"),
                "kind": sess.get("kind"),
                "role": resolve_admin_role(sess.get("platform"), sess.get("admin_user_id")),
                "createdAt": sess.get("activated_at") or sess.get("created_at"),
                "expiresAt": sess.get("expires_at"),
                "isCurrent": tok == current,
            })
        items.sort(key=lambda s: str(s.get("createdAt") or ""), reverse=True)
        return {"ok": True, "sessions": items}

    @router.post("/sessions/revoke")
    def revoke_session(payload: SessionRevokeRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, payload.token)
        _require(session, PERM_SYSTEM_MANAGE)
        raw = storage.list_admin_panel_sessions() if hasattr(storage, "list_admin_panel_sessions") else []
        target = next((s for s in raw if _session_token_id(s.get("token") or "") == payload.id), None)
        if target is None:
            raise HTTPException(status_code=404, detail="Сессия не найдена.")
        removed = bool(storage.delete_admin_panel_session(target.get("token")))
        record_admin_operation(
            session=session,
            action="session.revoke",
            target_type="admin_session",
            target_id=payload.id,
            target_name=str(target.get("admin_user_id") or ""),
            before={"scope": target.get("scope"), "expires_at": target.get("expires_at")},
            after={"revoked": removed},
            reason=payload.reason,
        )
        return {"ok": True, "removed": removed}

    # ---- Центр управления игроком (P1) -------------------------------------

    def _load_card(storage: Any, game_id: str) -> dict[str, Any] | None:
        detail = admin_player_detail(storage, game_id)
        if detail is None:
            return None
        # Активные штрафы — отдельным блоком карточки (read + forgive).
        try:
            from services.fine_service import active_fines

            player = storage.get_player_by_game_id(game_id) if hasattr(storage, "get_player_by_game_id") else None
            fines = active_fines(player) if isinstance(player, dict) else []
        except Exception:
            fines = []
        detail = dict(detail)
        detail["fines"] = [
            {
                "id": f.get("id"),
                "source": f.get("source_name") or f.get("source"),
                "amount": f.get("current_amount"),
                "day": f.get("current_day"),
                "status": f.get("status"),
            }
            for f in fines
            if isinstance(f, dict)
        ]
        return detail

    @router.get("/players")
    def get_players(
        request: Request,
        token: str | None = Query(default=None, min_length=16),
        q: str = "",
        limit: int = Query(default=200, ge=1, le=1000),
    ) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, token)
        _require(session, PERM_PLAYERS_VIEW)
        return {"ok": True, "players": list_admin_players(storage, query=q, limit=limit)}

    @router.get("/players/{game_id}")
    def get_player(game_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, token)
        _require(session, PERM_PLAYERS_VIEW)
        card = _load_card(storage, game_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Игрок не найден.")
        return {"ok": True, "player": card}

    @router.get("/players/{game_id}/logs")
    def get_player_logs(game_id: str, request: Request, token: str | None = Query(default=None, min_length=16), limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, token)
        _require(session, PERM_PLAYERS_VIEW)
        return {"ok": True, "logs": player_logs_last_24h(storage, game_id=game_id, limit=limit)}

    @router.get("/players/{game_id}/chat")
    def get_player_chat(game_id: str, request: Request, token: str | None = Query(default=None, min_length=16), limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, token)
        _require(session, PERM_PLAYERS_VIEW)
        return {"ok": True, "chat": player_chat_last_24h(storage, game_id=game_id, limit=limit)}

    @router.post("/players/{game_id}/view-token")
    def player_view_token(game_id: str, payload: PlayerActionRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, payload.token)
        # Этот токен даёт РЕДАКТИРУЕМЫЙ доступ к профилю игрока (выброс предметов,
        # смена имени, очки, курьер), поэтому требует права на изменение, а не
        # только players.view (Codex P1: read-only не должен получать edit-токен).
        _require(session, PERM_INVENTORY_EDIT)
        try:
            view_token = create_admin_player_view_token(storage, target_game_id=game_id, admin_session=session)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"ok": True, "token": view_token, "url": f"/admin_view_profile?token={view_token}"}

    @router.post("/players/{game_id}/rewards")
    def grant_rewards(game_id: str, payload: PlayerRewardRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, payload.token)
        _require(session, PERM_REWARDS_GRANT)
        card = _load_card(storage, game_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Игрок не найден.")
        rewards = [r.model_dump() for r in payload.rewards]
        # deliver_rewards_to_player сам пишет структурную операцию rewards.grant
        # (с ролью/причиной/до-после), поэтому здесь обёртка не нужна — иначе
        # одна выдача попала бы в аудит дважды.
        try:
            result = deliver_rewards_to_player(
                storage,
                target_game_id=game_id,
                rewards=rewards,
                admin_session=session,
                reason=payload.reason,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, **(result if isinstance(result, dict) else {})}

    @router.post("/players/{game_id}/message")
    def message_player(game_id: str, payload: PlayerMessageRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, payload.token)
        _require(session, PERM_PLAYERS_MESSAGE)
        card = _load_card(storage, game_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Игрок не найден.")
        from datetime import datetime, timezone

        message = {
            "type": "admin_message",
            "text": payload.text,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": "admin_panel_v2",
        }

        def _send() -> bool:
            from services.message_delivery import notify_player
            status = notify_player(
                storage, game_id, payload.text, type="admin_message",
                priority="high", source="admin_panel_v2", fallback_message=message,
            )
            if status == "skipped":
                player = storage.get_player_by_game_id(game_id)
                if not player:
                    raise ValueError("Игрок не найден.")
                player.setdefault("pending_bot_messages", []).append(message)
                storage.update_player(player)
            return True

        run_admin_operation(
            session=session,
            action="player.message",
            func=_send,
            target_type="player",
            target_id=game_id,
            target_name=card.get("name"),
            reason=payload.reason,
            details={"text": payload.text[:200]},
        )
        return {"ok": True}

    @router.post("/players/{game_id}/unstuck")
    def unstuck(game_id: str, payload: PlayerActionRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, payload.token)
        _require(session, PERM_PLAYERS_UNSTUCK)
        card = _load_card(storage, game_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Игрок не найден.")

        def _unstuck() -> str:
            from services.city_service import unstuck_player

            player = storage.get_player_by_game_id(game_id)
            if not player:
                raise ValueError("Игрок не найден.")
            # Админский разблок не должен упираться в 30-минутный кулдаун игрока.
            player["last_unstuck_at"] = 0
            response = unstuck_player(storage, player)
            return getattr(response, "text", "")

        text = run_admin_operation(
            session=session,
            action="player.unstuck",
            func=_unstuck,
            target_type="player",
            target_id=game_id,
            target_name=card.get("name"),
            before={"location": card.get("location")},
            after_func=lambda _r: _player_snapshot(admin_player_detail(storage, game_id)),
            reason=payload.reason,
        )
        return {"ok": True, "message": text}

    @router.post("/players/{game_id}/forgive-fine")
    def forgive_fine(game_id: str, payload: PlayerActionRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, payload.token)
        _require(session, PERM_FINES_MANAGE)
        card = _load_card(storage, game_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Игрок не найден.")
        before_fines = card.get("fines") or []

        def _forgive() -> dict[str, Any]:
            from services.fine_service import forgive_all_fines, repair_player_fines

            player = storage.get_player_by_game_id(game_id)
            if not player:
                raise ValueError("Игрок не найден.")
            actor = identity_key(session.get("platform"), session.get("admin_user_id"))
            result = forgive_all_fines(player, by=actor, reason=payload.reason)
            # §7: после снятия убеждаемся, что зависших ограничений не осталось.
            repair_player_fines(player)
            storage.update_player(player)
            return result

        result = run_admin_operation(
            session=session,
            action="fines.forgive",
            func=_forgive,
            target_type="player",
            target_id=game_id,
            target_name=card.get("name"),
            before={"fines": before_fines},
            after_func=lambda r: {"fines": [], "removed": r.get("removed"), "wasForced": r.get("was_forced")},
            reason=payload.reason,
        )
        return {"ok": True, "forgiven": int((result or {}).get("removed") or 0)}

    @router.post("/players/{game_id}/repair-fines")
    def repair_fines(game_id: str, payload: PlayerActionRequest, request: Request) -> dict[str, Any]:
        # §6: «Проверить штрафы игрока» — найти и починить зависшие/несогласованные
        # штрафы (терминальные, что висят как активные; устаревший legacy-алиас).
        storage = get_storage()
        session = _session(storage, request, payload.token)
        _require(session, PERM_FINES_MANAGE)
        card = _load_card(storage, game_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Игрок не найден.")

        def _repair() -> dict[str, Any]:
            from services.fine_service import repair_player_fines

            player = storage.get_player_by_game_id(game_id)
            if not player:
                raise ValueError("Игрок не найден.")
            report = repair_player_fines(player)
            if report.get("fixed"):
                storage.update_player(player)
            return report

        report = run_admin_operation(
            session=session,
            action="fines.repair",
            func=_repair,
            target_type="player",
            target_id=game_id,
            target_name=card.get("name"),
            after_func=lambda r: {"state": r.get("state"), "issues": r.get("issues"), "fixed": r.get("fixed")},
            reason=payload.reason,
        )
        return {"ok": True, "report": report}

    @router.post("/players/{game_id}/reset")
    def reset_player(game_id: str, payload: PlayerActionRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, payload.token)
        _require(session, PERM_PLAYERS_RESET)
        card = _load_card(storage, game_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Игрок не найден.")

        def _reset() -> str:
            ok, message, _player = reset_player_progress(storage, game_id)
            if not ok:
                raise ValueError(message)
            return message

        try:
            message = run_admin_operation(
                session=session,
                action="player.reset",
                func=_reset,
                target_type="player",
                target_id=game_id,
                target_name=card.get("name"),
                before=_player_snapshot(card),
                after_func=lambda _r: _player_snapshot(admin_player_detail(storage, game_id)),
                reason=payload.reason,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "message": message}

    @router.delete("/players/{game_id}")
    def delete_player(game_id: str, payload: PlayerDeleteRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, payload.token)
        _require(session, PERM_PLAYERS_DELETE)
        if payload.confirm != "CONFIRM_DELETE":
            raise HTTPException(status_code=400, detail="Для удаления нужно подтверждение CONFIRM_DELETE.")
        card = _load_card(storage, game_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Игрок не найден.")

        def _delete() -> str:
            ok, message, _player = delete_player_profile(storage, game_id)
            if not ok:
                raise ValueError(message)
            return message

        try:
            message = run_admin_operation(
                session=session,
                action="player.delete",
                func=_delete,
                target_type="player",
                target_id=game_id,
                target_name=card.get("name"),
                before={"name": card.get("name"), "level": card.get("level")},
                after_func=lambda _r: {"deleted": True},
                reason=payload.reason,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "message": message}

    return router
