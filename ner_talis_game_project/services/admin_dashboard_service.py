"""Сводка для dashboard админ-панели (ТЗ 11 §16).

Собирает дешёвые агрегаты по конструкторам/реестру/аудиту для главной страницы:
счётчики сущностей, активные ошибки/связи/изображения, последние изменения,
активные мировые события, последний импорт. Каждый блок считается best-effort —
сбой одного источника не роняет всю сводку.
"""

from __future__ import annotations

from typing import Any

# (ключ, подпись, источник) — источник возвращает список envelope'ов с полем status.
# Реестр мира и EntityStore-конструкторы перечислены отдельно в _constructor_stats.


def _entity_stats(records: list[dict[str, Any]]) -> dict[str, int]:
    total = len(records)
    published = sum(1 for r in records if (r.get("status") == "published"))
    errors = sum(1 for r in records if (r.get("status") == "error"))
    drafts = sum(1 for r in records if (r.get("status") == "draft"))
    return {"total": total, "published": published, "errors": errors, "drafts": drafts}


def _safe(fn) -> Any:
    try:
        return fn()
    except Exception:
        return None


def _constructor_stats() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def add(key: str, label: str, section: str, records: list[dict[str, Any]] | None) -> None:
        if records is None:
            return
        out.append({"key": key, "label": label, "section": section, **_entity_stats(records)})

    def _store_list(module_name: str) -> list[dict[str, Any]] | None:
        import importlib

        try:
            module = importlib.import_module(f"services.{module_name}")
            return module.store().list()
        except Exception:
            return None

    def _wcr_list(const_name: str) -> list[dict[str, Any]] | None:
        try:
            from services import world_content_registry as wcr

            kconst = getattr(wcr, const_name)
            return wcr.list_content(kconst)
        except Exception:
            return None

    add("item", "Предметы", "items", _store_list("item_constructor_service"))
    add("effect", "Эффекты", "effects", _store_list("effect_constructor_service"))
    add("mob", "Мобы", "world", _wcr_list("KIND_MOB"))
    add("location", "Локации", "world", _wcr_list("KIND_LOCATION"))
    add("event", "События", "world", _wcr_list("KIND_EVENT"))
    add("achievement", "Достижения", "achievements", _store_list("achievement_service"))
    add("recipe", "Рецепты", "recipes", _store_list("recipe_constructor_service"))
    add("reputation", "Репутации", "reputations", _store_list("reputation_constructor_service"))
    add("text", "Тексты бота", "texts", _store_list("text_constructor_service"))
    return out


def _recent_changes(limit: int = 12) -> list[dict[str, Any]]:
    from services.admin_audit import read_admin_audit_records

    rows = read_admin_audit_records(limit=limit)
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({
            "action": r.get("action"),
            "target_type": r.get("target_type"),
            "target_id": r.get("target_id"),
            "actor": r.get("admin_user_id") or r.get("actor"),
            "role": r.get("role"),
            "at": r.get("created_at") or r.get("at") or r.get("timestamp"),
            "status": r.get("status"),
            "dangerous": r.get("dangerous"),
        })
    return out


def _active_world_events() -> int:
    from services import world_event_service as wes

    items = wes.store().list()
    return sum(1 for e in items if (e.get("status") == "active"))


def _players_count(storage: Any) -> int | None:
    if storage is None:
        return None
    try:
        rows = storage.list_player_audience_rows()
        return len(rows) if rows is not None else None
    except Exception:
        return None


def summary(storage: Any = None) -> dict[str, Any]:
    """Полная сводка dashboard (ТЗ 11 §16). Все блоки best-effort."""
    stats = _safe(_constructor_stats) or []
    link_check = _safe(lambda: __import__("services.constructor_import", fromlist=["check_import"]).check_import())
    images = _safe(lambda: __import__("services.image_audit_service", fromlist=["audit"]).audit())
    last_import = _safe(lambda: __import__("services.constructor_import", fromlist=["load_last_report"]).load_last_report())

    total_objects = sum(s.get("total", 0) for s in stats)
    error_objects = sum(s.get("errors", 0) for s in stats)
    draft_objects = sum(s.get("drafts", 0) for s in stats)

    return {
        "players": _players_count(storage),
        "totals": {
            "objects": total_objects,
            "errors": error_objects,
            "drafts": draft_objects,
            "link_issues": (link_check or {}).get("count", 0) if link_check else 0,
            "image_issues": ((images or {}).get("missing", 0) + (images or {}).get("external", 0)) if images else 0,
            "active_world_events": _safe(_active_world_events) or 0,
        },
        "constructors": stats,
        "recent_changes": _safe(_recent_changes) or [],
        "last_import": (last_import or {}).get("summary") if last_import else None,
    }
