"""Конструктор лагеря V2 (доп. ТЗ §4) — авторская часть.

Лагерь — отдельная настраиваемая механика отдыха игрока в локациях: текст,
восстановление (HP/мана/дух/энергия), время отдыха, доступные действия, особые
события, привязка к локациям. Это слой данных + валидация; рантайм отдыха —
services/external_location_service.py (лагерь/готовка). Хранение — генерик
EntityStore (data/camp_constructor.json). Аудит и права (camp.*) — в роутере
admin_camp_api. Существующие лагеря заводятся constructor_import.import_camps.
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore

# --- Статусы (как у остальных конструкторов) --------------------------------
STATUS_DRAFT = "draft"
STATUS_REVIEW = "review"
STATUS_READY = "ready"
STATUS_PUBLISHED = "published"
STATUS_DISABLED = "disabled"
STATUS_ARCHIVE = "archive"
STATUS_ERROR = "error"

STATUSES = (STATUS_DRAFT, STATUS_REVIEW, STATUS_READY, STATUS_PUBLISHED, STATUS_DISABLED, STATUS_ARCHIVE, STATUS_ERROR)
STATUS_LABELS = {
    STATUS_DRAFT: "Черновик", STATUS_REVIEW: "На проверке", STATUS_READY: "Готов к публикации",
    STATUS_PUBLISHED: "Опубликован", STATUS_DISABLED: "Отключён", STATUS_ARCHIVE: "Архив",
    STATUS_ERROR: "Ошибка проверки",
}
TRANSITIONS: dict[str, set[str]] = {
    STATUS_DRAFT: {STATUS_REVIEW, STATUS_READY, STATUS_ARCHIVE, STATUS_ERROR},
    STATUS_REVIEW: {STATUS_DRAFT, STATUS_READY, STATUS_ARCHIVE, STATUS_ERROR},
    STATUS_READY: {STATUS_DRAFT, STATUS_PUBLISHED, STATUS_ARCHIVE, STATUS_ERROR},
    STATUS_PUBLISHED: {STATUS_DISABLED, STATUS_ARCHIVE},
    STATUS_DISABLED: {STATUS_PUBLISHED, STATUS_DRAFT, STATUS_ARCHIVE},
    STATUS_ARCHIVE: {STATUS_DRAFT},
    STATUS_ERROR: {STATUS_DRAFT, STATUS_REVIEW, STATUS_ARCHIVE},
}

# --- Справочники (доп. ТЗ §4) -----------------------------------------------
CAMP_TYPES = (
    "standard", "starting", "safe", "temporary", "event", "military",
    "seeker", "bandit", "hunter", "fishing", "crafting", "trade", "quest",
    "hidden", "abandoned", "cursed", "dangerous", "technical", "special",
)
CAMP_TYPE_LABELS = {
    "standard": "Стандартный", "safe": "Безопасный", "dangerous": "Опасный",
    "event": "Событийный", "temporary": "Временный", "special": "Специальный",
}
CAMP_CATEGORIES = (
    "safe_point", "respawn_point", "rest_point", "transition_point",
    "service_point", "npc_point", "quest_point", "event_point",
    "recovery_point", "protection_point", "technical_point",
)
SAFETY_TYPES = ("safe", "partial", "dangerous")
RECOVERY_TARGETS = ("hp", "mana", "spirit", "energy", "stamina", "fatigue")
CAMP_ACTIONS = (
    "rest", "restore_hp", "restore_energy", "restore_mana", "restore_spirit",
    "inspect", "cook", "use_item", "talk_npc", "check_gear", "special_event",
    "leave", "back",
)

_HTML_RE = re.compile(r"<[^>]+>")

_store = EntityStore(
    env_var="CAMP_CONSTRUCTOR_PATH",
    default_rel="data/camp_constructor.json",
    statuses=STATUSES,
    transitions=TRANSITIONS,
    initial_status=STATUS_DRAFT,
)


def store() -> EntityStore:
    return _store


def _str(data: dict[str, Any], key: str) -> str:
    return str(data.get(key) or "").strip()


def _has_markup(value: str) -> bool:
    return "<script" in value.lower() or bool(_HTML_RE.search(value))


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    """Проверка лагеря перед публикацией (доп. ТЗ §4.2–§4.6)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not _str(data, "name"):
        errors.append("Не заполнено название лагеря.")
    camp_type = _str(data, "camp_type")
    if camp_type and camp_type not in CAMP_TYPES:
        errors.append(f"Неизвестный тип лагеря: {camp_type}.")
    category = _str(data, "category")
    if category and category not in CAMP_CATEGORIES:
        errors.append(f"Неизвестная категория лагеря: {category}.")
    safety = _str(data, "safety_type")
    if safety and safety not in SAFETY_TYPES:
        errors.append(f"Неизвестный режим безопасности лагеря: {safety}.")

    locations = data.get("locations") or []
    if isinstance(locations, str):
        locations = [part.strip() for part in locations.split(",") if part.strip()]
    parent_location = _str(data, "parent_location")
    location_ids = {str(value).strip() for value in locations if str(value).strip()}
    if parent_location:
        location_ids.add(parent_location)
    if not location_ids:
        errors.append("Не выбрана родительская локация лагеря.")
    else:
        try:
            from services import world_content_registry as world

            missing = [location_id for location_id in location_ids if world.get_content(world.KIND_LOCATION, location_id) is None]
            if missing:
                errors.append("Не найдены родительские локации лагеря: " + ", ".join(sorted(missing)) + ".")
            sublocation = _str(data, "parent_sublocation")
            if sublocation and world.get_content(world.KIND_SUBLOCATION, sublocation) is None:
                errors.append(f"Родительская подлокация «{sublocation}» не найдена.")
        except Exception as exc:
            warnings.append(f"Не удалось проверить связи лагеря с миром: {exc}")

    # Восстановление (§4.3).
    recovery = data.get("recovery")
    if isinstance(recovery, list):
        for i, row in enumerate(recovery, start=1):
            if not isinstance(row, dict):
                errors.append(f"Восстановление {i}: неверный формат.")
                continue
            target = str(row.get("target") or "").strip()
            if target and target not in RECOVERY_TARGETS:
                errors.append(f"Восстановление {i}: неизвестная цель «{target}».")
            for key in ("flat", "percent", "per_minute", "min", "max"):
                val = _num(row.get(key))
                if val is not None and val < 0:
                    errors.append(f"Восстановление {i}: «{key}» не может быть отрицательным.")
            mn = _num(row.get("min"))
            mx = _num(row.get("max"))
            if mn is not None and mx is not None and mn > mx:
                errors.append(f"Восстановление {i}: мин. больше макс.")
    elif recovery not in (None, ""):
        errors.append("Восстановление должно быть списком.")

    # Время (§4.4).
    for key in ("base_time", "min_time", "max_time", "cooldown", "use_limit", "rest_price", "rest_item_amount"):
        val = _num(data.get(key))
        if data.get(key) not in (None, "") and (val is None or val < 0):
            errors.append(f"Поле «{key}» не может быть отрицательным.")
    min_t = _num(data.get("min_time"))
    max_t = _num(data.get("max_time"))
    if min_t is not None and max_t is not None and min_t > max_t:
        errors.append("Минимальное время больше максимального.")
    if data.get("can_rest") and not recovery:
        errors.append("Отдых включён, но не настроено восстановление ресурсов.")
    if (data.get("use_as_respawn") or data.get("return_after_death") or data.get("death_camp")) and not _str(data, "death_return_text"):
        errors.append("Для точки возврата после смерти не заполнен текст возврата.")

    # Действия (§4.5).
    actions = data.get("actions")
    if isinstance(actions, list):
        for act in actions:
            if str(act) not in CAMP_ACTIONS:
                warnings.append(f"Действие «{act}» не из стандартного списка.")

    for key in ("name", "full_text", "short_description"):
        value = _str(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустим HTML.")

    # Списочные связи карточки (§7–§15).
    relation_specs = (
        ("npc_ids", "NPC", "npc"), ("event_ids", "событие", "event"),
        ("button_ids", "кнопка", "button"), ("weekly_limit_ids", "лимит", "location_weekly_limit"),
    )
    try:
        from services import world_content_registry as world

        for field, label, kind in relation_specs:
            for value in data.get(field) or []:
                ref_id = str((value or {}).get("id") if isinstance(value, dict) else value).strip()
                if ref_id and world.get_content(kind, ref_id) is None:
                    errors.append(f"Связь лагеря: {label} «{ref_id}» не найден(а).")
        for index, row in enumerate(data.get("camp_events") or [], start=1):
            if not isinstance(row, dict):
                errors.append(f"Событие лагеря {index}: неверный формат.")
                continue
            event_id = str(row.get("event_id") or "").strip()
            if not event_id or world.get_content(world.KIND_EVENT, event_id) is None:
                errors.append(f"Событие лагеря {index}: событие «{event_id or '—'}» не найдено.")
            chance = _num(row.get("chance"))
            if chance is None or chance < 0 or chance > 100:
                errors.append(f"Событие лагеря {index}: шанс должен быть 0–100.")
        for index, row in enumerate(data.get("weekly_limits") or [], start=1):
            if not isinstance(row, dict):
                errors.append(f"Недельный лимит {index}: неверный формат.")
                continue
            maximum = _num(row.get("max_per_week"))
            if maximum is None or maximum < 0:
                errors.append(f"Недельный лимит {index}: максимум не может быть отрицательным.")
    except Exception:
        pass
    try:
        from services.item_registry import get_item_definition_by_id
        from services import effect_constructor_service as effects

        condition_types = {"level", "race", "item", "quest", "event", "reputation", "hidden_reputation", "fine", "unlock", "flag", "state"}
        for index, row in enumerate(data.get("access_conditions") or [], start=1):
            if not isinstance(row, dict):
                errors.append(f"Условие доступа {index}: неверный формат.")
                continue
            condition_type = str(row.get("type") or row.get("condition_type") or "")
            if condition_type not in condition_types:
                errors.append(f"Условие доступа {index}: неизвестный тип «{condition_type or '—'}».")
            operator = str(row.get("operator") or "eq")
            if operator not in {"eq", "ne", "gte", "lte", "gt", "lt"}:
                errors.append(f"Условие доступа {index}: неизвестный оператор «{operator}».")
            ref_id = str(row.get("object_id") or row.get("id") or "").strip()
            if condition_type not in {"level"} and not ref_id:
                errors.append(f"Условие доступа {index}: не выбран связанный объект.")
            if condition_type == "item" and ref_id and get_item_definition_by_id(ref_id) is None:
                errors.append(f"Условие доступа {index}: предмет «{ref_id}» не существует.")

        for row in data.get("items") or []:
            item_id = str((row or {}).get("item_id") or "") if isinstance(row, dict) else str(row or "")
            if item_id and get_item_definition_by_id(item_id) is None:
                errors.append(f"Предмет лагеря «{item_id}» не существует.")
        rest_item_id = _str(data, "rest_item_id")
        if rest_item_id and get_item_definition_by_id(rest_item_id) is None:
            errors.append(f"Предмет для отдыха «{rest_item_id}» не существует.")
        for row in data.get("effect_links") or []:
            effect_id = str((row or {}).get("effect_id") or "") if isinstance(row, dict) else str(row or "")
            env = effects.store().get(effect_id) if effect_id else None
            if effect_id and (not env or env.get("status") != effects.STATUS_PUBLISHED):
                errors.append(f"Эффект лагеря «{effect_id}» не найден или не опубликован.")
        for index, raw in enumerate(data.get("services") or [], start=1):
            row = raw if isinstance(raw, dict) else {"service_id": str(raw), "name": str(raw)}
            if not str(row.get("service_id") or "").strip() or not str(row.get("name") or "").strip():
                errors.append(f"Услуга лагеря {index}: нужны ID и название.")
            cost = _num(row.get("cost"))
            if cost is not None and cost < 0:
                errors.append(f"Услуга лагеря {index}: цена не может быть отрицательной.")
            item_id = str(row.get("required_item_id") or "").strip()
            if item_id and get_item_definition_by_id(item_id) is None:
                errors.append(f"Услуга лагеря {index}: предмет «{item_id}» не существует.")
            effect_id = str(row.get("effect_id") or "").strip()
            if effect_id:
                env = effects.store().get(effect_id)
                if not env or env.get("status") != effects.STATUS_PUBLISHED:
                    errors.append(f"Услуга лагеря {index}: эффект «{effect_id}» не найден или не опубликован.")
    except Exception:
        pass

    if not _str(data, "full_text"):
        warnings.append("Не заполнено полное описание лагеря.")
    if not data.get("npc_ids"):
        warnings.append("В лагере нет NPC.")
    if not data.get("event_ids"):
        warnings.append("В лагере нет событий.")
    if data.get("can_rest") and not data.get("weekly_limit_ids") and not data.get("weekly_limits"):
        warnings.append("Отдых включён без недельного лимита.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def published_for_location(location_id: str) -> list[dict[str, Any]]:
    """Опубликованные лагеря, привязанные к локации (для выбора в конструкторе
    локаций, §4.8)."""
    lid = str(location_id or "").strip()
    out: list[dict[str, Any]] = []
    for env in _store.list(status=STATUS_PUBLISHED):
        data = env.get("data") or {}
        locs = data.get("locations") or []
        if not lid or (isinstance(locs, list) and lid in [str(x) for x in locs]):
            out.append({"id": env.get("id"), "name": data.get("name"), "camp_type": data.get("camp_type")})
    return out


def where_used(camp_id: str) -> dict[str, Any]:
    """Связи лагеря, показываемые UI и блокирующие полное удаление."""
    camp_id = str(camp_id or "").strip()
    envelope = _store.get(camp_id)
    usages: list[dict[str, Any]] = []
    if not envelope:
        return {"id": camp_id, "items": usages, "total": 0}
    data = envelope.get("data") or {}

    locations = data.get("locations") or []
    if isinstance(locations, str):
        locations = [part.strip() for part in locations.split(",")]
    parent_location = str(data.get("parent_location") or "").strip()
    if parent_location:
        locations = [*locations, parent_location]
    for location_id in sorted({str(value).strip() for value in locations if str(value).strip()}):
        usages.append({"kind": "location", "id": location_id, "name": location_id, "path": "locations"})
    sublocation_id = str(data.get("parent_sublocation") or data.get("sublocation_id") or "").strip()
    if sublocation_id:
        usages.append({"kind": "sublocation", "id": sublocation_id, "name": sublocation_id, "path": "parent_sublocation"})
    if data.get("use_as_respawn") or data.get("return_after_death") or data.get("death_camp"):
        usages.append({"kind": "death", "id": camp_id, "name": "Возврат после смерти", "path": "death_camp"})

    try:
        from services import world_content_registry as world

        for kind in world.KINDS:
            for source in world.list_content(kind):
                source_data = source.get("data") or {}
                paths: list[str] = []

                def walk(value: Any, path: str = "data") -> None:
                    if isinstance(value, dict):
                        for key, child in value.items():
                            child_path = f"{path}.{key}"
                            if key in {"camp", "camp_id", "target_camp", "death_camp_id", "return_camp_id"} and str(child or "") == camp_id:
                                paths.append(child_path)
                            walk(child, child_path)
                    elif isinstance(value, list):
                        for index, child in enumerate(value):
                            walk(child, f"{path}[{index}]")

                walk(source_data)
                if kind == world.KIND_BUTTON and source_data.get("action") == "open_camp" and str(source_data.get("target") or "") == camp_id:
                    paths.append("data.target")
                if paths:
                    usages.append({
                        "kind": kind, "id": source.get("id"),
                        "name": source_data.get("name") or source_data.get("text") or source.get("id"),
                        "path": ", ".join(sorted(set(paths))),
                    })
    except Exception:
        pass
    return {"id": camp_id, "items": usages, "total": len(usages)}
