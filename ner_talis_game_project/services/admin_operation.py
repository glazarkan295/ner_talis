"""Единая модель изменяющей админской операции (V2).

Любое изменяющее действие админ-панели проходит через эту прослойку: она
фиксирует кто/что/над кем/причину/значение до и после/статус и пишет
структурную запись в аудит. Так выполняется требование ТЗ §22 «admin_operation».

Использование на эндпоинте:

    role = require_permission(session, PERM_...)          # из admin_rbac
    before = snapshot(player)
    ... мутация ...
    after = snapshot(player)
    record_admin_operation(session=session, action="player.money_change",
                           target_type="player", target_id=gid, target_name=name,
                           before=before, after=after, reason=reason)

или обёрткой run_admin_operation(...).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from services.admin_audit import append_admin_audit_record
from services.admin_rbac import (
    DANGEROUS_ACTIONS,
    role_for_session,
)

STATUS_OK = "ok"
STATUS_ERROR = "error"


def is_dangerous_action(action: str) -> bool:
    return str(action or "") in DANGEROUS_ACTIONS


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _admin_name(session: dict[str, Any] | None) -> str:
    if not isinstance(session, dict):
        return ""
    return str(
        session.get("admin_name")
        or session.get("admin_user_id")
        or session.get("admin_key")
        or ""
    )


def build_operation_record(
    *,
    session: dict[str, Any] | None,
    action: str,
    target_type: str | None = None,
    target_id: Any = None,
    target_name: str | None = None,
    before: Any = None,
    after: Any = None,
    reason: str = "",
    status: str = STATUS_OK,
    error: Any = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    session = session if isinstance(session, dict) else {}
    record: dict[str, Any] = {
        "created_at": _now_iso(),
        "platform": session.get("platform"),
        "admin_user_id": str(session.get("admin_user_id") or ""),
        "admin_name": _admin_name(session),
        "admin_role": role_for_session(session),
        "action": str(action or ""),
        "target_type": str(target_type or ""),
        "target_id": str(target_id or ""),
        "target_name": str(target_name or ""),
        "before": before,
        "after": after,
        "reason": str(reason or ""),
        "status": str(status or STATUS_OK),
        "error": str(error) if error else "",
        "session_id": str(session.get("token") or session.get("session_id") or ""),
        "dangerous": is_dangerous_action(action),
    }
    if details:
        record["details"] = details
    return record


def record_admin_operation(**kwargs: Any) -> dict[str, Any]:
    """Построить и записать в аудит одну админ-операцию. Возвращает запись."""
    record = build_operation_record(**kwargs)
    append_admin_audit_record(record)
    return record


def run_admin_operation(
    *,
    session: dict[str, Any] | None,
    action: str,
    func: Callable[[], Any],
    target_type: str | None = None,
    target_id: Any = None,
    target_name: str | None = None,
    before: Any = None,
    after_func: Callable[[Any], Any] | None = None,
    reason: str = "",
    details: dict[str, Any] | None = None,
) -> Any:
    """Выполнить мутацию ``func`` и записать операцию (ok/error) в аудит.

    При исключении пишет запись со статусом error и пробрасывает исключение.
    """
    try:
        result = func()
    except Exception as exc:  # noqa: BLE001 - намеренно логируем любую ошибку
        record_admin_operation(
            session=session, action=action, target_type=target_type,
            target_id=target_id, target_name=target_name, before=before,
            reason=reason, status=STATUS_ERROR, error=exc, details=details,
        )
        raise
    after = after_func(result) if callable(after_func) else None
    record_admin_operation(
        session=session, action=action, target_type=target_type,
        target_id=target_id, target_name=target_name, before=before,
        after=after, reason=reason, status=STATUS_OK, details=details,
    )
    return result
