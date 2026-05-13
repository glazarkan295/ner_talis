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
