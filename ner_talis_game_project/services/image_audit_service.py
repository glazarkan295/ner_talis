"""Аудит изображений импортированного контента (full-import ТЗ §6).

Сканирует поля-картинки у сущностей конструкторов/реестра мира и проверяет, что
файл существует в статическом/рантайм-хранилище. ТЗ §6: изображения должны быть
файлами, а не внешними ссылками; отсутствующие — помечаются в отчёте и
предупреждением в админ-панели.

Статусы поля: ok (файл найден) / missing (локальный путь, файла нет) /
external (внешняя ссылка или data:-URI — недопустимо, нужен локальный ассет) /
empty (поле пустое — пропускается). Пути не переписываются: старые пути
сохраняются, отчёт лишь сообщает, что нужно перезалить/поправить.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from project_paths import resolve_project_path

_EXTERNAL_RE = re.compile(r"^(?:[a-z][a-z0-9+.-]*:)?//", re.IGNORECASE)

# Поля-картинки у EntityStore-конструкторов: kind → (имя модуля, поля).
_ENTITY_IMAGE_FIELDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "item": ("item_constructor_service", ("icon", "model_image", "image")),
    "race": ("race_constructor_service", ("model_image", "image")),
    "city_node": ("city_constructor_service", ("image",)),
}
# Поля-картинки у реестра мира: kind → (имя константы вида, поля).
_WCR_IMAGE_FIELDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "mob": ("KIND_MOB", ("image",)),
    "location": ("KIND_LOCATION", ("image", "image_path")),
    "event": ("KIND_EVENT", ("image",)),
    "npc": ("KIND_NPC", ("image",)),
    "button": ("KIND_BUTTON", ("image",)),
}


def _roots() -> dict[str, Path]:
    web = resolve_project_path("web")
    uploads = resolve_project_path(os.getenv("PUBLIC_UPLOADS_ASSETS_DIR", "data/public_uploads/assets"))
    return {"dist": web / "dist" / "assets", "public": web / "public" / "assets", "uploads": uploads}


def _candidate_files(value: str, roots: dict[str, Path]) -> list[Path]:
    """Возможные пути на диске для локального ассета (учитывает оба хранилища)."""
    cleaned = str(value or "").strip()
    if cleaned.startswith("web/public/"):
        cleaned = cleaned[len("web/public/"):]
    cleaned = cleaned.lstrip("/")
    if not cleaned.startswith("assets/"):
        return []
    rel = cleaned[len("assets/"):]  # путь после assets/
    if rel.startswith("admin_uploads/"):
        return [roots["uploads"] / rel]
    return [roots["dist"] / rel, roots["public"] / rel]


def classify(value: Any, roots: dict[str, Path] | None = None) -> str:
    """Статус одного значения поля-картинки."""
    text = str(value or "").strip()
    if not text:
        return "empty"
    if text.lower().startswith("data:") or _EXTERNAL_RE.match(text):
        return "external"
    roots = roots or _roots()
    candidates = _candidate_files(text, roots)
    if not candidates:
        # Локальный, но не из assets/ — не можем проверить, считаем отсутствующим.
        return "missing"
    return "ok" if any(p.is_file() for p in candidates) else "missing"


def _scan_records(kind: str, records: list[dict[str, Any]], fields: tuple[str, ...],
                  roots: dict[str, Path], entries: list[dict[str, Any]]) -> None:
    for env in records:
        data = env.get("data") or {}
        for field in fields:
            value = str(data.get(field) or "").strip()
            if not value:
                continue
            status = classify(value, roots)
            if status == "empty":
                continue
            entries.append({
                "kind": kind, "id": env.get("id"), "field": field,
                "value": value, "status": status,
            })


def audit() -> dict[str, Any]:
    """Полный аудит изображений (ТЗ §6). Возвращает сводку + списки проблем."""
    import importlib

    roots = _roots()
    entries: list[dict[str, Any]] = []

    for kind, (module_name, fields) in _ENTITY_IMAGE_FIELDS.items():
        try:
            module = importlib.import_module(f"services.{module_name}")
            records = module.store().list()
        except Exception:
            continue
        _scan_records(kind, records, fields, roots, entries)

    try:
        from services import world_content_registry as wcr

        for kind, (const_name, fields) in _WCR_IMAGE_FIELDS.items():
            kconst = getattr(wcr, const_name, None)
            if not kconst:
                continue
            _scan_records(kind, wcr.list_content(kconst), fields, roots, entries)
    except Exception:
        pass

    by_status: dict[str, int] = {"ok": 0, "missing": 0, "external": 0}
    for e in entries:
        by_status[e["status"]] = by_status.get(e["status"], 0) + 1
    problems = [e for e in entries if e["status"] in ("missing", "external")]
    return {
        "total": len(entries),
        "ok": by_status.get("ok", 0),
        "missing": by_status.get("missing", 0),
        "external": by_status.get("external", 0),
        "problems": problems,
        "entries": entries,
    }
