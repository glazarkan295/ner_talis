"""Генерик-хранилище админских сущностей V2 (гильдии, мировые события).

Маленький переиспользуемый слой данных: один JSON-файл с блокировкой на тип
сущности, единый envelope и управляемый жизненный цикл статусов. Аудит и права
делает роутер через admin_operation — стор остаётся чистым.

Envelope: id/data/status/created_at/created_by/updated_at/updated_by/version.
По духу повторяет world_content_registry, но для сущностей со своими наборами
статусов (у гильдий и событий они разные).
"""

from __future__ import annotations

import json
import os
import re
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

try:  # POSIX-блокировка (на Windows отсутствует)
    import fcntl
except Exception:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

from project_paths import project_path, resolve_project_path

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{1,63}$")


class EntityError(ValueError):
    """Ошибка операции стора (не найдено / дубликат / запрещённый переход)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EntityStore:
    """Хранилище одного типа сущностей в отдельном JSON-файле с блокировкой."""

    def __init__(
        self,
        *,
        env_var: str,
        default_rel: str,
        statuses: tuple[str, ...],
        transitions: dict[str, set[str]],
        initial_status: str,
    ) -> None:
        self._env_var = env_var
        self._default_rel = default_rel
        self.statuses = statuses
        self.transitions = transitions
        self.initial_status = initial_status
        self._lock = threading.Lock()

    # --- пути и ввод/вывод ---
    def path(self) -> Path:
        override = os.getenv(self._env_var)
        if override:
            return resolve_project_path(override)
        parts = self._default_rel.split("/")
        return project_path(*parts)

    def _load(self) -> dict[str, Any]:
        try:
            with self.path().open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict[str, Any]) -> None:
        path = self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        tmp.replace(path)

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        if fcntl is None:
            yield
            return
        path = self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_suffix(path.suffix + ".lock")
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    # --- чтение ---
    def list(self, *, status: str | None = None) -> list[dict[str, Any]]:
        with self._lock, self._file_lock():
            bucket = self._load()
        items = [v for v in bucket.values() if isinstance(v, dict)]
        if status:
            items = [v for v in items if v.get("status") == status]
        items.sort(key=lambda v: str(v.get("updated_at") or ""), reverse=True)
        return items

    def get(self, entity_id: str) -> dict[str, Any] | None:
        with self._lock, self._file_lock():
            obj = self._load().get(str(entity_id))
        return obj if isinstance(obj, dict) else None

    # --- мутации ---
    def create(self, entity_id: str, data: dict[str, Any], *, actor: str = "") -> dict[str, Any]:
        entity_id = str(entity_id or "").strip()
        if not _ID_RE.match(entity_id):
            raise EntityError(
                "ID должен быть из латиницы/цифр/подчёркиваний (2–64 символа), "
                "начинаться с буквы или цифры."
            )
        with self._lock, self._file_lock():
            store = self._load()
            if entity_id in store:
                raise EntityError(f"Объект {entity_id} уже существует.")
            now = _now_iso()
            envelope = {
                "id": entity_id,
                "status": self.initial_status,
                "data": data if isinstance(data, dict) else {},
                "created_at": now,
                "created_by": str(actor or ""),
                "updated_at": now,
                "updated_by": str(actor or ""),
                "version": 1,
            }
            store[entity_id] = envelope
            self._save(store)
            return dict(envelope)

    def update(self, entity_id: str, data: dict[str, Any], *, actor: str = "") -> dict[str, Any]:
        entity_id = str(entity_id)
        with self._lock, self._file_lock():
            store = self._load()
            envelope = store.get(entity_id)
            if not isinstance(envelope, dict):
                raise EntityError(f"Объект {entity_id} не найден.")
            merged = dict(envelope.get("data") or {})
            merged.update(data if isinstance(data, dict) else {})
            envelope["data"] = merged
            envelope["updated_at"] = _now_iso()
            envelope["updated_by"] = str(actor or "")
            envelope["version"] = int(envelope.get("version") or 1) + 1
            store[entity_id] = envelope
            self._save(store)
            return dict(envelope)

    def set_status(self, entity_id: str, status: str, *, actor: str = "", force: bool = False) -> dict[str, Any]:
        if status not in self.statuses:
            raise EntityError(f"Неизвестный статус: {status}.")
        entity_id = str(entity_id)
        with self._lock, self._file_lock():
            store = self._load()
            envelope = store.get(entity_id)
            if not isinstance(envelope, dict):
                raise EntityError(f"Объект {entity_id} не найден.")
            current = str(envelope.get("status") or self.initial_status)
            if not force and status != current and status not in self.transitions.get(current, set()):
                raise EntityError(f"Недопустимый переход статуса: {current} → {status}.")
            envelope["status"] = status
            envelope["updated_at"] = _now_iso()
            envelope["updated_by"] = str(actor or "")
            store[entity_id] = envelope
            self._save(store)
            return dict(envelope)
