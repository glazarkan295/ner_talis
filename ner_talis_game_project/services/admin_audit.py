"""Аудит административных действий."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from project_paths import resolve_project_path


def _audit_path():
    return resolve_project_path(os.getenv("ADMIN_AUDIT_LOG_PATH", "data/admin_audit.log"))


def write_admin_audit(*, platform: str, admin_user_id: str | int, command: str, action: str, details: dict[str, Any] | None = None) -> None:
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform,
        "admin_user_id": str(admin_user_id),
        "command": command,
        "action": action,
        "details": details or {},
    }
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def append_admin_audit_record(record: dict[str, Any]) -> None:
    """Дописать готовую структурную запись аудита (admin_operation V2)."""
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(record)
    payload.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _normalize_audit_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Привести записи (старого write_admin_audit и нового V2) к одному виду."""
    details = raw.get("details") if isinstance(raw.get("details"), dict) else {}
    return {
        "created_at": raw.get("created_at"),
        "platform": raw.get("platform"),
        "admin_user_id": str(raw.get("admin_user_id") or raw.get("admin_id") or ""),
        "admin_name": raw.get("admin_name") or "",
        "admin_role": raw.get("admin_role") or raw.get("role") or "",
        "action": raw.get("action") or raw.get("command") or "",
        "target_type": raw.get("target_type") or "",
        "target_id": str(raw.get("target_id") or details.get("game_id") or details.get("target_game_id") or ""),
        "target_name": raw.get("target_name") or "",
        "reason": raw.get("reason") or "",
        "status": raw.get("status") or "ok",
        "error": raw.get("error") or "",
        "before": raw.get("before"),
        "after": raw.get("after"),
        "session_id": raw.get("session_id") or "",
        # V2 records carry a precomputed "dangerous" flag; legacy records don't.
        "dangerous": bool(raw.get("dangerous")),
        "details": details,
    }


def read_admin_audit_records(
    *,
    limit: int = 200,
    offset: int = 0,
    since: Any = None,
    until: Any = None,
    admin_user_id: str | None = None,
    role: str | None = None,
    action: str | None = None,
    action_prefix: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    dangerous_actions: set[str] | None = None,
    dangerous_only: bool = False,
    errors_only: bool = False,
) -> list[dict[str, Any]]:
    """Прочитать журнал аудита с фильтрами, новые записи первыми."""
    path = _audit_path()
    if not path.exists():
        return []
    since_dt = _parse_dt(since)
    until_dt = _parse_dt(until)
    dangerous_actions = dangerous_actions or set()
    records: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(raw, dict):
                    continue
                records.append(_normalize_audit_record(raw))
    except OSError:
        return []

    def _keep(rec: dict[str, Any]) -> bool:
        created = _parse_dt(rec.get("created_at"))
        if since_dt and (created is None or created < since_dt):
            return False
        if until_dt and (created is None or created > until_dt):
            return False
        if admin_user_id and rec.get("admin_user_id") != str(admin_user_id):
            return False
        if role and rec.get("admin_role") != role:
            return False
        if action and rec.get("action") != action:
            return False
        if action_prefix and not str(rec.get("action") or "").startswith(action_prefix):
            return False
        if target_type and rec.get("target_type") != target_type:
            return False
        if target_id and rec.get("target_id") != str(target_id):
            return False
        if dangerous_only and rec.get("action") not in dangerous_actions:
            return False
        if errors_only and rec.get("status") == "ok":
            return False
        return True

    filtered = [rec for rec in records if _keep(rec)]
    filtered.reverse()  # newest first
    start = max(0, int(offset))
    end = start + max(1, int(limit))
    return filtered[start:end]
