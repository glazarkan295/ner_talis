"""Импорт-миграция существующего статического контента в реестры конструкторов.

Цель (ТЗ §3): админ должен видеть в конструкторах уже существующие игровые
сущности (предметы, мобы, …), а не только новые V2-черновики. Этот слой читает
живые игровые данные и заводит их как ОПУБЛИКОВАННЫЕ записи в сторах
конструкторов.

Принципы:
* идемпотентность — повторный запуск не плодит дубликаты (пропускает уже
  существующие id);
* аддитивность — живые data/*.json не трогаются, читаются только на чтение;
* безопасность — по умолчанию (overwrite=False) НЕ перетираем правки админа;
  с overwrite=True обновляются только ранее импортированные записи
  (data.imported is True), рукотворные записи никогда не трогаются;
* маркировка — у импортированных записей data.imported=True + import_source +
  source_id, чтобы отличать их и переимпортировать безопасно.
"""

from __future__ import annotations

import re
from typing import Any

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{1,63}$")


def safe_constructor_id(raw: Any) -> str:
    """Привести исходный id к формату реестра (латиница/цифры/подчёркивание)."""
    text = re.sub(r"[^a-z0-9_]+", "_", str(raw or "").strip().lower())
    text = re.sub(r"_+", "_", text).strip("_")
    return text if _ID_RE.match(text) else ""


# Кириллица → латиница: каталог навыков (active_skills_registry) хранит id
# по-русски, и обычный safe_constructor_id вырезал бы все буквы (728 разных
# навыков схлопнулись бы в ~53 id). Транслитерация сохраняет уникальность.
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def translit_constructor_id(raw: Any) -> str:
    """Транслитерировать кириллический id в латинский id формата реестра."""
    text = str(raw or "").strip().lower()
    text = "".join(_TRANSLIT.get(ch, ch) for ch in text)
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")[:64].strip("_")
    return text if _ID_RE.match(text) else ""


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _was_imported(existing: dict[str, Any]) -> bool:
    return bool((existing.get("data") or {}).get("imported"))


# --- Предметы --------------------------------------------------------------
def _map_item(definition: dict[str, Any], source_id: str) -> dict[str, Any]:
    max_stack = definition.get("max_stack")
    stackable = definition.get("stackable")
    if stackable is None:
        try:
            stackable = int(max_stack) > 1
        except (TypeError, ValueError):
            stackable = False
    return {
        "name": definition.get("name") or definition.get("name_ru") or source_id,
        "short_description": definition.get("short_description") or "",
        "description": definition.get("description") or definition.get("desc") or "",
        "category": definition.get("category") or "",
        "item_type": definition.get("item_type") or definition.get("type") or "",
        "quality": definition.get("quality") or "",
        "price_buy": definition.get("price_buy") or definition.get("buy_price"),
        "price_sell": definition.get("price_sell") or definition.get("sell_price"),
        "stackable": bool(stackable),
        "max_stack": max_stack,
        "equip_slot": definition.get("equip_slot") or definition.get("slot") or "",
        "icon": definition.get("icon") or definition.get("image") or "",
        "imported": True,
        "import_source": "item_registry",
        "source_id": str(definition.get("id") or definition.get("item_id") or source_id),
        "source_raw": definition,
    }


def import_items(*, overwrite: bool = False, actor: str = "import", mode: str | None = None) -> dict[str, Any]:
    from services.item_registry import load_all_item_definitions
    from services import item_constructor_service as ics

    overwrite = overwrite or _mode_is_overwrite(mode)
    store = ics.store()
    created = updated = skipped = invalid = 0
    for definition in load_all_item_definitions():
        if not isinstance(definition, dict):
            invalid += 1
            continue
        sid = safe_constructor_id(definition.get("id") or definition.get("item_id") or definition.get("name"))
        if not sid:
            invalid += 1
            continue
        data = _map_item(definition, sid)
        existing = store.get(sid)
        if existing is not None:
            if overwrite and _was_imported(existing):
                store.update(sid, data, actor=actor)
                updated += 1
            else:
                skipped += 1
            continue
        store.create(sid, data, actor=actor)
        try:
            store.set_status(sid, ics.STATUS_PUBLISHED, actor=actor, force=True)
        except Exception:
            pass
        created += 1
    return {"kind": "item", "created": created, "updated": updated, "skipped": skipped, "invalid": invalid}


# --- Мобы ------------------------------------------------------------------
def _map_mob_drop(loot: Any) -> list[dict[str, Any]]:
    if not isinstance(loot, (list, tuple)):
        return []
    try:
        from services.item_registry import get_item_definition_by_name
    except Exception:
        get_item_definition_by_name = None  # type: ignore[assignment]
    rows: list[dict[str, Any]] = []
    for entry in loot:
        if not isinstance(entry, (list, tuple)) or len(entry) < 1:
            continue
        name = str(entry[0])
        chance = entry[1] if len(entry) > 1 else 0
        mn = entry[2] if len(entry) > 2 else 1
        mx = entry[3] if len(entry) > 3 else mn
        item_id = ""
        if get_item_definition_by_name is not None:
            try:
                d = get_item_definition_by_name(name)
                item_id = str((d or {}).get("id") or (d or {}).get("item_id") or "")
            except Exception:
                item_id = ""
        rows.append({"item_id": item_id, "name": name, "chance": chance, "min_count": mn, "max_count": mx})
    return rows


_DAMAGE_TO_ATTACK = {"physical": "physical", "magic": "magical", "mixed": "mixed"}


def _map_mob(template: dict[str, Any], source_id: str) -> dict[str, Any]:
    damage_type = str(_enum_value(template.get("damage_type")) or "physical").lower()
    hp_base = template.get("hp_base")
    try:
        hp = int(hp_base) if hp_base is not None else 30
    except (TypeError, ValueError):
        hp = 30
    return {
        "name": template.get("name") or source_id,
        "type": str(template.get("biological_type") or "monster"),
        "hp": hp,
        "attack_type": _DAMAGE_TO_ATTACK.get(damage_type, "physical"),
        "description": template.get("text") or "",
        "role": str(template.get("role") or ""),
        "skills": list(template.get("skills") or []),
        "features": list(template.get("features") or []),
        "drop": _map_mob_drop(template.get("loot")),
        "imported": True,
        "import_source": "battle_catalog",
        "source_id": source_id,
    }


def import_mobs(*, overwrite: bool = False, actor: str = "import", mode: str | None = None) -> dict[str, Any]:
    from services.pve_battle_service import BATTLE_MOB_CATALOGS
    from services import world_content_registry as wcr

    overwrite = overwrite or _mode_is_overwrite(mode)
    created = updated = skipped = invalid = 0
    seen: set[str] = set()
    for catalog in BATTLE_MOB_CATALOGS.values():
        if not isinstance(catalog, dict):
            continue
        for mob_key, template in catalog.items():
            sid = safe_constructor_id(mob_key)
            if not sid or sid in seen:
                if sid:
                    seen.add(sid)
                else:
                    invalid += 1
                continue
            seen.add(sid)
            if not isinstance(template, dict):
                invalid += 1
                continue
            data = _map_mob(template, sid)
            existing = wcr.get_content(wcr.KIND_MOB, sid)
            if existing is not None:
                if overwrite and _was_imported(existing):
                    wcr.update_content(wcr.KIND_MOB, sid, data, actor=actor)
                    updated += 1
                else:
                    skipped += 1
                continue
            wcr.create_content(wcr.KIND_MOB, sid, data, actor=actor)
            try:
                wcr.set_status(wcr.KIND_MOB, sid, wcr.STATUS_PUBLISHED, actor=actor, force=True)
            except Exception:
                pass
            created += 1
    return {"kind": "mob", "created": created, "updated": updated, "skipped": skipped, "invalid": invalid}


# --- Эффекты / состояния / проклятия (сид существующих, ТЗ §6/§7) ----------
# Игровые эффекты разбросаны по коду (стимулятор/проклятья/сопротивления), без
# единого JSON-реестра. Сид-таблица заводит известные состояния и проклятия как
# опубликованные записи конструктора, чтобы их можно было править/копировать.
# (effect_id, Название, effect_type, отрицательный?, источник)
_EFFECT_SEED = [
    # Состояния (§6)
    ("poison", "Отравление", "periodic_damage", True, "mob"),
    ("bleed", "Кровотечение", "periodic_damage", True, "mob"),
    ("stun", "Оглушение", "control_effect", True, "mob"),
    ("burn", "Поджог", "periodic_damage", True, "mob"),
    ("freeze", "Заморозка", "control_effect", True, "mob"),
    ("slow", "Замедление", "stat_modifier", True, "mob"),
    ("blind", "Слепота", "accuracy_modifier", True, "mob"),
    ("weakness", "Слабость", "stat_modifier", True, "mob"),
    ("exhaustion", "Истощение", "stat_modifier", True, "zone"),
    ("regeneration", "Регенерация", "resource_regeneration", False, "item"),
    ("defense_up", "Защита", "physical_defense_modifier", False, "skill"),
    ("empower", "Усиление", "stat_modifier", False, "skill"),
    ("rage", "Ярость", "stat_modifier", False, "skill"),
    ("fear", "Испуг", "control_effect", True, "mob"),
    ("silence", "Молчание", "control_effect", True, "mob"),
    ("disarm", "Обезоруживание", "control_effect", True, "mob"),
    ("sleep", "Сон", "control_effect", True, "mob"),
    ("paralysis", "Паралич", "control_effect", True, "mob"),
    ("cursed_mark", "Проклятая метка", "curse_effect", True, "curse"),
    ("debtor_mark", "Метка должника", "curse_effect", True, "trap"),
    ("battle_stimulant", "Боевой стимулятор", "stat_modifier", False, "item"),
    ("cleanse", "Очищение", "stat_modifier", False, "item"),
    ("effect_immunity", "Иммунитет к эффекту", "damage_response", False, "item"),
    ("effect_resistance", "Сопротивление эффекту", "damage_response", False, "item"),
    # Проклятия (§7)
    ("ancient_curse", "Древнее проклятье", "curse_effect", True, "curse"),
    ("pvp_death_curse", "Проклятье погибшего игрока", "curse_effect", True, "curse"),
    ("zone_curse", "Проклятье зоны", "curse_effect", True, "zone"),
    ("item_curse", "Проклятье предмета", "curse_effect", True, "item"),
    ("event_curse", "Проклятье события", "curse_effect", True, "event"),
    ("trap_curse", "Проклятье ловушки", "curse_effect", True, "trap"),
    ("mob_curse", "Проклятье моба", "curse_effect", True, "mob"),
    ("wrong_choice_curse", "Проклятье после неправильного выбора", "curse_effect", True, "event"),
    ("blood_curse", "Проклятье крови", "curse_effect", True, "curse"),
    ("spirit_curse", "Проклятье духа", "curse_effect", True, "curse"),
    ("mana_curse", "Проклятье маны", "curse_effect", True, "curse"),
    ("luck_curse", "Проклятье удачи", "curse_effect", True, "curse"),
    ("loot_curse", "Проклятье добычи", "curse_effect", True, "curse"),
    ("path_curse", "Проклятье пути", "curse_effect", True, "curse"),
]


def import_effects(*, overwrite: bool = False, actor: str = "import", mode: str | None = None) -> dict[str, Any]:
    from services import effect_constructor_service as ecs

    overwrite = overwrite or _mode_is_overwrite(mode)
    store = ecs.store()
    created = updated = skipped = 0
    for effect_id, name, effect_type, negative, source in _EFFECT_SEED:
        data = {
            "effect_name": name, "effect_type": effect_type, "source_type": source,
            "target": "self", "active_when": "always", "stack_rule": "strongest_only",
            "negative": bool(negative), "show_to_player": True,
            "imported": True, "import_source": "effect_seed", "source_id": effect_id,
        }
        existing = store.get(effect_id)
        if existing is not None:
            if overwrite and _was_imported(existing):
                store.update(effect_id, data, actor=actor)
                updated += 1
            else:
                skipped += 1
            continue
        store.create(effect_id, data, actor=actor)
        try:
            store.set_status(effect_id, ecs.STATUS_PUBLISHED, actor=actor, force=True)
        except Exception:
            pass
        created += 1
    return {"kind": "effect", "created": created, "updated": updated, "skipped": skipped, "invalid": 0}


# --- Навыки (импорт каталога путей, ТЗ §7) ---------------------------------
# Каталог навыков (data/active_skills_registry.json) хранит ветви/пути по-русски
# (Дух/Мана, Меч/Огонь…). Сводим их к кодам конструктора, чтобы записи проходили
# валидацию skill_constructor_service.
_BRANCH_TO_CODE = {"Дух": "spirit", "spirit": "spirit", "Мана": "mana", "mana": "mana"}
_PATH_TO_CODE = {
    "Меч": "sword", "Кинжал": "dagger", "Топор": "axe", "Молот": "hammer",
    "Лук": "bow", "Щит": "shield", "Арбалет": "crossbow",
    "Огонь": "fire", "Вода": "water", "Земля": "earth", "Воздух": "air",
    "Поддержка": "support", "Смерть": "death", "Жизнь": "life",
}


def _map_skill(skill: dict[str, Any], source_id: str) -> dict[str, Any]:
    from services import active_skill_service as ass

    runtime = ass.runtime_skill_from_catalog(skill)
    is_passive = str(runtime.get("skill_type") or "").casefold() == "passive"
    branch = _BRANCH_TO_CODE.get(str(runtime.get("branch") or "").strip(), "neutral")
    path = _PATH_TO_CODE.get(str(runtime.get("path") or "").strip(), "none")
    weapons = runtime.get("weapon_requirements") or ["any"]
    if isinstance(weapons, str):
        weapons = [weapons]
    resource = str(runtime.get("resource") or "none")
    if resource not in ("none", "spirit", "mana"):
        resource = "none"
    damage = str(runtime.get("damage_type") or "none")
    if damage not in ("none", "physical", "magic", "mixed"):
        damage = "none"
    modifiers = [
        {"name": str(m.get("name") or ""), "effect": str(m.get("effect") or "")}
        for m in (runtime.get("modifiers") or []) if isinstance(m, dict)
    ]
    return {
        "name": runtime.get("name") or source_id,
        "skill_type": "passive" if is_passive else "active",
        "branch": branch,
        "path": path,
        "resource_type": resource,
        "resource_cost": int(runtime.get("base_resource_cost") or 0),
        "cooldown_turns": int(runtime.get("cooldown_turns") or 0),
        "damage_type": damage,
        "target_mode": "passive" if is_passive else str(runtime.get("target_mode") or "single_enemy"),
        "weapon_requirements": [str(w) for w in weapons],
        "unlock_path_level": int(runtime.get("unlock_path_level") or 0),
        "choice_index": int(runtime.get("choice_index") or 0),
        "description": str(runtime.get("description") or ""),
        "base_damage_formula": runtime.get("base_damage_formula") or "",
        "modifiers": modifiers,
        "imported": True,
        "import_source": "active_skills_registry",
        "source_id": str(skill.get("id") or source_id),
    }


def import_skills(*, overwrite: bool = False, actor: str = "import", mode: str | None = None) -> dict[str, Any]:
    from services import active_skill_service as ass
    from services import skill_constructor_service as scs

    overwrite = overwrite or _mode_is_overwrite(mode)
    store = scs.store()
    created = updated = skipped = invalid = 0
    for skill in ass.all_catalog_skills():
        if not isinstance(skill, dict):
            invalid += 1
            continue
        sid = translit_constructor_id(skill.get("id") or skill.get("name")) or safe_constructor_id(skill.get("id") or skill.get("name"))
        if not sid:
            invalid += 1
            continue
        data = _map_skill(skill, sid)
        existing = store.get(sid)
        if existing is not None:
            if overwrite and _was_imported(existing):
                store.update(sid, data, actor=actor)
                updated += 1
            else:
                skipped += 1
            continue
        store.create(sid, data, actor=actor)
        try:
            store.set_status(sid, scs.STATUS_PUBLISHED, actor=actor, force=True)
        except Exception:
            pass
        created += 1
    return {"kind": "skill", "created": created, "updated": updated, "skipped": skipped, "invalid": invalid}


# --- Режимы повторного импорта (ТЗ §8) + общий отчёт (§6/§7) ----------------
IMPORT_MODES = ("new", "update", "copy", "skip", "overwrite")
MODE_LABELS = {
    "new": "Добавить только новые данные",
    "update": "Обновить существующие данные",
    "copy": "Создать копии",
    "skip": "Пропустить уже существующие",
    "overwrite": "Перезаписать (ручные правки защищены)",
}


def _resolve_mode(mode: str | None, overwrite: bool = False) -> str:
    if mode:
        value = str(mode).strip().lower()
        return value if value in IMPORT_MODES else "new"
    return "update" if overwrite else "new"


def _mode_is_overwrite(mode: str | None) -> bool:
    return _resolve_mode(mode) in ("update", "overwrite")


def _rich_report(kind: str) -> dict[str, Any]:
    return {"kind": kind, "found": 0, "created": 0, "updated": 0, "skipped": 0,
            "invalid": 0, "errors": [], "needs_check": []}


def _normalize_report(report: dict[str, Any]) -> dict[str, Any]:
    """Привести отчёт старых импортёров к единой форме (доп. ключи аддитивно)."""
    out = dict(report)
    out.setdefault("errors", [])
    out.setdefault("needs_check", [])
    out.setdefault("found", out.get("created", 0) + out.get("updated", 0) + out.get("skipped", 0) + out.get("invalid", 0))
    return out


def _copy_id(sid: str, exists: Any) -> str:
    base = f"{sid}_copy"
    if not exists(base):
        return base
    for n in range(2, 100):
        cand = f"{base}{n}"
        if not exists(cand):
            return cand
    return ""


def _apply_record(report, sid, data, mode, *, get_fn, create_fn, update_fn, publish_fn) -> None:
    """Создать/обновить/скопировать/пропустить запись с защитой ручных правок (§9)."""
    report["found"] += 1
    existing = get_fn(sid)
    if existing is not None:
        if mode in ("new", "skip"):
            report["skipped"] += 1
            return
        if not _was_imported(existing) and mode != "copy":
            report["skipped"] += 1
            report["needs_check"].append({
                "id": sid, "type": report["kind"],
                "reason": "Изменено вручную в админ-панели — не перезаписано. Выберите режим «Создать копии» или подтвердите перезапись.",
            })
            return
        if mode == "copy":
            new_id = _copy_id(sid, lambda x: get_fn(x) is not None)
            if not new_id:
                report["invalid"] += 1
                report["errors"].append({"id": sid, "type": report["kind"], "reason": "Не удалось подобрать id для копии."})
                return
            create_fn(new_id, data)
            publish_fn(new_id)
            report["created"] += 1
            return
        update_fn(sid, data)
        report["updated"] += 1
        return
    create_fn(sid, data)
    publish_fn(sid)
    report["created"] += 1


def _wcr_funcs(kind: str, actor: str):
    from services import world_content_registry as wcr

    def publish(sid):
        try:
            wcr.set_status(kind, sid, wcr.STATUS_PUBLISHED, actor=actor, force=True)
        except Exception:
            pass

    return (
        lambda sid: wcr.get_content(kind, sid),
        lambda sid, data: wcr.create_content(kind, sid, data, actor=actor),
        lambda sid, data: wcr.update_content(kind, sid, data, actor=actor),
        publish,
    )


def _store_funcs(store: Any, published_status: str, actor: str):
    def publish(sid):
        try:
            store.set_status(sid, published_status, actor=actor, force=True)
        except Exception:
            pass

    return (
        lambda sid: store.get(sid),
        lambda sid, data: store.create(sid, data, actor=actor),
        lambda sid, data: store.update(sid, data, actor=actor),
        publish,
    )


def _read_data_json(filename: str) -> Any:
    from project_paths import project_path
    import json

    path = project_path("data", filename)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


# --- Импорт локаций (ТЗ §3) -------------------------------------------------
# (файл, тип локации по умолчанию). Источники — живые data/*.json локаций.
_LOCATION_FILES = [
    ("hilly_meadows.json", "wild"),
    ("ordinary_forest.json", "wild"),
    ("small_plateau_location.json", "wild"),
    ("fortress_in_gorge.json", "fortress"),
    ("seldar_city.json", "city"),
]


def import_locations(*, mode: str | None = None, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    from services import world_content_registry as wcr

    report = _rich_report("location")
    mode = _resolve_mode(mode, overwrite)
    get_fn, create_fn, update_fn, publish_fn = _wcr_funcs(wcr.KIND_LOCATION, actor)
    for filename, default_type in _LOCATION_FILES:
        data_raw = _read_data_json(filename)
        if not isinstance(data_raw, dict):
            report["errors"].append({"id": filename, "type": "location", "reason": "Файл локации отсутствует или повреждён."})
            continue
        raw_id = data_raw.get("id") or data_raw.get("location_id") or data_raw.get("city_id") or filename.rsplit(".", 1)[0]
        sid = safe_constructor_id(raw_id)
        if not sid:
            report["invalid"] += 1
            report["errors"].append({"id": str(raw_id), "type": "location", "reason": "Не удалось получить корректный id."})
            continue
        name = data_raw.get("name") or data_raw.get("name_ru") or sid
        desc = data_raw.get("short_description") or data_raw.get("description") or data_raw.get("entry_text") or data_raw.get("lore_description") or ""
        record = {
            "name": name, "type": default_type,
            "short_description": str(desc)[:300], "description": str(desc),
            "imported": True, "import_source": f"data/{filename}", "source_id": str(raw_id),
        }
        _apply_record(report, sid, record, mode, get_fn=get_fn, create_fn=create_fn, update_fn=update_fn, publish_fn=publish_fn)
    return report


# --- Импорт событий локаций (ТЗ §3) -----------------------------------------
_EVENT_TYPE_MAP = {
    "trap": "trap", "battle": "met_mob", "glint": "rare_find",
    "berries": "found_resource", "alchemy_ingredient": "found_resource", "stone_or_ore": "found_resource",
}


def import_events(*, mode: str | None = None, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    from services import world_content_registry as wcr

    report = _rich_report("event")
    mode = _resolve_mode(mode, overwrite)
    get_fn, create_fn, update_fn, publish_fn = _wcr_funcs(wcr.KIND_EVENT, actor)
    placeholder_text = False
    for filename in ("hilly_meadows.json", "ordinary_forest.json"):
        data_raw = _read_data_json(filename)
        if not isinstance(data_raw, dict):
            continue
        loc_id = safe_constructor_id(data_raw.get("id") or data_raw.get("location_id") or filename.rsplit(".", 1)[0])
        events = data_raw.get("events")
        if not isinstance(events, dict):
            continue
        for ev_name, chance in events.items():
            evsid = safe_constructor_id(f"{loc_id}_{ev_name}")
            if not evsid:
                report["invalid"] += 1
                continue
            try:
                ch = float(chance)
            except (TypeError, ValueError):
                ch = 0.0
            record = {
                "name": str(ev_name), "type": _EVENT_TYPE_MAP.get(str(ev_name), "found_resource"),
                "text": f"Событие локации: {ev_name}.", "chance": ch, "location": loc_id,
                "imported": True, "import_source": f"data/{filename}", "source_id": str(ev_name),
            }
            before = report["created"] + report["updated"]
            _apply_record(report, evsid, record, mode, get_fn=get_fn, create_fn=create_fn, update_fn=update_fn, publish_fn=publish_fn)
            if report["created"] + report["updated"] > before:
                placeholder_text = True
    if placeholder_text:
        report["needs_check"].append({
            "id": "events", "type": "event",
            "reason": "У событий текст-заглушка (в исходных данных только шанс) — задайте текст/исход вручную.",
        })
    return report


# --- Импорт узлов города (ТЗ §4) --------------------------------------------
def import_city_nodes(*, mode: str | None = None, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    from services import city_constructor_service as ccs

    report = _rich_report("city_node")
    mode = _resolve_mode(mode, overwrite)
    get_fn, create_fn, update_fn, publish_fn = _store_funcs(ccs.store(), ccs.STATUS_PUBLISHED, actor)
    data_raw = _read_data_json("seldar_city.json")
    if not isinstance(data_raw, dict):
        report["errors"].append({"id": "seldar_city.json", "type": "city_node", "reason": "Файл города отсутствует или повреждён."})
        return report
    city_id = safe_constructor_id(data_raw.get("city_id") or "seldar")
    _apply_record(report, city_id, {
        "_kind": ccs.KIND_NODE,
        "name": data_raw.get("name") or "Селдар", "node_type": "city", "description": "",
        "imported": True, "import_source": "data/seldar_city.json", "source_id": str(data_raw.get("city_id") or "seldar"),
    }, mode, get_fn=get_fn, create_fn=create_fn, update_fn=update_fn, publish_fn=publish_fn)
    zones = data_raw.get("zones")
    if isinstance(zones, dict):
        for zid, zone in zones.items():
            if not isinstance(zone, dict):
                continue
            sid = safe_constructor_id(zid)
            if not sid:
                report["invalid"] += 1
                continue
            _apply_record(report, sid, {
                "_kind": ccs.KIND_NODE,
                "name": zone.get("name") or zid, "node_type": "quarter", "parent_id": city_id, "description": "",
                "imported": True, "import_source": "data/seldar_city.json", "source_id": str(zid),
            }, mode, get_fn=get_fn, create_fn=create_fn, update_fn=update_fn, publish_fn=publish_fn)
    return report


# --- Проверка целостности импорта (ТЗ §10) ----------------------------------
def check_import() -> dict[str, Any]:
    """Сканирует реестры конструкторов и находит проблемы связей/полей."""
    from services import world_content_registry as wcr
    from services import city_constructor_service as ccs
    from services import item_constructor_service as ics

    issues: list[dict[str, Any]] = []
    loc_ids = {e.get("id") for e in wcr.list_content(wcr.KIND_LOCATION)}
    for ev in wcr.list_content(wcr.KIND_EVENT):
        loc = str((ev.get("data") or {}).get("location") or "")
        if not loc:
            issues.append({"type": "event", "id": ev.get("id"), "reason": "Событие без локации."})
        elif loc not in loc_ids:
            issues.append({"type": "event", "id": ev.get("id"), "reason": f"Локация «{loc}» не найдена."})

    city_items = ccs.store().list()
    node_ids = {i.get("id") for i in city_items if (i.get("data") or {}).get("_kind") == ccs.KIND_NODE}
    for item in city_items:
        data = item.get("data") or {}
        kind = data.get("_kind")
        if kind == ccs.KIND_NODE:
            parent = str(data.get("parent_id") or "")
            if parent and parent not in node_ids:
                issues.append({"type": "city_node", "id": item.get("id"), "reason": f"Родительский узел «{parent}» не найден."})
        elif kind == ccs.KIND_BUTTON:
            if not str(data.get("action") or ""):
                issues.append({"type": "city_button", "id": item.get("id"), "reason": "Кнопка без действия."})
            target = str(data.get("target_node_id") or "")
            if target and target not in node_ids:
                issues.append({"type": "city_button", "id": item.get("id"), "reason": f"Переход в несуществующий узел «{target}»."})
        elif kind in (ccs.KIND_SHOP_ITEM, ccs.KIND_SERVICE, ccs.KIND_CRIMINAL):
            nid = str(data.get("node_id") or "")
            if nid and nid not in node_ids:
                issues.append({"type": kind, "id": item.get("id"), "reason": f"Привязка к несуществующему узлу «{nid}»."})

    for it in ics.store().list():
        if not str((it.get("data") or {}).get("category") or ""):
            issues.append({"type": "item", "id": it.get("id"), "reason": "Предмет без категории."})

    return {"ok": not issues, "count": len(issues), "issues": issues}


# --- Оркестратор -----------------------------------------------------------
IMPORTERS = {
    "item": import_items, "mob": import_mobs, "effect": import_effects, "skill": import_skills,
    "location": import_locations, "event": import_events, "city_node": import_city_nodes,
}


def import_all(kinds: list[str] | None = None, *, overwrite: bool = False, mode: str | None = None, actor: str = "import") -> dict[str, Any]:
    selected = [k for k in (kinds or list(IMPORTERS)) if k in IMPORTERS]
    reports = [_normalize_report(IMPORTERS[k](overwrite=overwrite, mode=mode, actor=actor)) for k in selected]
    summary = {
        "found": sum(r["found"] for r in reports),
        "created": sum(r["created"] for r in reports),
        "updated": sum(r["updated"] for r in reports),
        "skipped": sum(r["skipped"] for r in reports),
        "invalid": sum(r["invalid"] for r in reports),
        "errors": sum(len(r["errors"]) for r in reports),
        "needs_check": sum(len(r["needs_check"]) for r in reports),
        "mode": _resolve_mode(mode, overwrite),
    }
    return {"ok": True, "reports": reports, "summary": summary}
