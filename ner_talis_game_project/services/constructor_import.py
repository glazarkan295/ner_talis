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


# --- Dry-run (ТЗ §3.3, §16: «нельзя делать импорт без dry-run») -------------
# Глобальный флаг + контекст-скоуп: на время симуляции все записи в сторы
# (create/update/publish) подменяются no-op, а счётчики/needs_check заполняются
# как при реальном импорте. Так dry-run переиспользует ту же логику без дубля.
_DRY_RUN = {"on": False}

# Журнал созданных записей последнего РЕАЛЬНОГО импорта (ТЗ §4.1: откат
# последнего импорта). Заполняется в момент создания записи; import_all
# сбрасывает его в начале и сохраняет в файл по завершении реального прогона.
_BATCH: list[tuple[str, str]] = []


def _record_created(kind: str, sid: str) -> None:
    if not _DRY_RUN["on"]:
        _BATCH.append((str(kind), str(sid)))


def _noop(*_args: Any, **_kwargs: Any) -> None:
    return None


class _dry_run_scope:  # noqa: N801 — контекст-менеджер в стиле snake_case
    def __init__(self, on: bool) -> None:
        self._on = bool(on)
        self._prev = False

    def __enter__(self) -> "_dry_run_scope":
        self._prev = _DRY_RUN["on"]
        _DRY_RUN["on"] = self._on
        return self

    def __exit__(self, *exc: Any) -> None:
        _DRY_RUN["on"] = self._prev


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

    if _resolve_mode(mode) == "copy":
        return _copy_unsupported("item")
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
        data.setdefault("legacy_id", data.get("source_id") or sid)
        blocked = _DRY_RUN["on"]
        existing = store.get(sid)
        if existing is not None:
            if overwrite and _was_imported(existing):
                if not blocked:
                    store.update(sid, data, actor=actor)
                updated += 1
            else:
                skipped += 1
            continue
        if not blocked:
            store.create(sid, data, actor=actor)
            try:
                store.set_status(sid, ics.STATUS_PUBLISHED, actor=actor, force=True)
            except Exception:
                pass
        _record_created("item", sid)
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

    if _resolve_mode(mode) == "copy":
        return _copy_unsupported("mob")
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
            data.setdefault("legacy_id", data.get("source_id") or sid)
            blocked = _DRY_RUN["on"]
            existing = wcr.get_content(wcr.KIND_MOB, sid)
            if existing is not None:
                if overwrite and _was_imported(existing):
                    if not blocked:
                        wcr.update_content(wcr.KIND_MOB, sid, data, actor=actor)
                    updated += 1
                else:
                    skipped += 1
                continue
            if not blocked:
                wcr.create_content(wcr.KIND_MOB, sid, data, actor=actor)
                try:
                    wcr.set_status(wcr.KIND_MOB, sid, wcr.STATUS_PUBLISHED, actor=actor, force=True)
                except Exception:
                    pass
            _record_created("mob", sid)
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

    if _resolve_mode(mode) == "copy":
        return _copy_unsupported("effect")
    overwrite = overwrite or _mode_is_overwrite(mode)
    store = ecs.store()
    created = updated = skipped = 0
    needs_check: list[dict[str, Any]] = []

    def _publish_if_valid(effect_id: str, data: dict[str, Any]) -> bool:
        # Публикуем ТОЛЬКО валидные сиды: часть состояний/проклятий требует
        # тип-специфичных полей (stat для stat_modifier, control_kind для
        # control_effect, resource для регенерации), которых в сиде нет. Раньше
        # их публиковали force=True → реестр держал эффекты, которые обычный
        # publish-эндпоинт отверг бы, а рантайм получал бы неполные записи.
        if not ecs.validate({"data": data})["ok"]:
            return False
        if not _DRY_RUN["on"]:
            try:
                store.set_status(effect_id, ecs.STATUS_PUBLISHED, actor=actor, force=True)
            except Exception:
                pass
        return True

    for effect_id, name, effect_type, negative, source in _EFFECT_SEED:
        data = {
            "effect_name": name, "effect_type": effect_type, "source_type": source,
            "target": "self", "active_when": "always", "stack_rule": "strongest_only",
            "negative": bool(negative), "show_to_player": True, "player_text": name,
            "imported": True, "import_source": "effect_seed", "source_id": effect_id,
            "legacy_id": effect_id,
        }
        blocked = _DRY_RUN["on"]
        existing = store.get(effect_id)
        if existing is not None:
            if overwrite and _was_imported(existing):
                if not blocked:
                    store.update(effect_id, data, actor=actor)
                _publish_if_valid(effect_id, data)
                updated += 1
            else:
                skipped += 1
            continue
        if not blocked:
            store.create(effect_id, data, actor=actor)
        if not _publish_if_valid(effect_id, data):
            needs_check.append({
                "id": effect_id, "type": "effect",
                "reason": "Сид без обязательных полей типа (stat/control_kind/resource) — оставлен черновиком, дополните и опубликуйте.",
            })
        _record_created("effect", effect_id)
        created += 1
    return {"kind": "effect", "created": created, "updated": updated, "skipped": skipped, "invalid": 0, "needs_check": needs_check}


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

    if _resolve_mode(mode) == "copy":
        return _copy_unsupported("skill")
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
        data.setdefault("legacy_id", data.get("source_id") or sid)
        blocked = _DRY_RUN["on"]
        existing = store.get(sid)
        if existing is not None:
            if overwrite and _was_imported(existing):
                if not blocked:
                    store.update(sid, data, actor=actor)
                updated += 1
            else:
                skipped += 1
            continue
        if not blocked:
            store.create(sid, data, actor=actor)
            try:
                store.set_status(sid, scs.STATUS_PUBLISHED, actor=actor, force=True)
            except Exception:
                pass
        _record_created("skill", sid)
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


def _copy_unsupported(kind: str) -> dict[str, Any]:
    """Отчёт-отказ: режим «копии» не поддержан для сид/каталог-импортёров.

    item/mob/effect/skill импортируются из кода/каталогов без отдельных
    исходных id, поэтому осмысленной «копии» у них нет. Раньше copy молча
    схлопывался в new и существующие записи просто пропускались — админ видел
    «успех», но копий не появлялось. Возвращаем явный needs_check."""
    return {
        "kind": kind, "created": 0, "updated": 0, "skipped": 0, "invalid": 0,
        "needs_check": [{
            "id": kind, "type": kind,
            "reason": "Режим «Создать копии» не поддерживается для этого импорта. Используйте «Добавить новые» или «Обновить».",
        }],
    }


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


def _apply_record(report, sid, data, mode, *, get_fn, create_fn, update_fn, publish_fn, copy_rewrite=None) -> None:
    """Создать/обновить/скопировать/пропустить запись с защитой ручных правок (§9).

    copy_rewrite(data) -> data — для режима «копия» переписывает ссылки на
    скопированные записи (например, location/parent_id → их копии), иначе копия
    оставалась бы привязанной к оригиналам.

    В dry-run (ТЗ §3.3, §16) запись в сторы подменяется no-op: счётчики и
    needs_check заполняются как при реальном импорте, но ничего не пишется."""
    # legacy_id (ТЗ §2/§3, AC#3): стабильный технический id старой сущности рядом
    # с записью. По умолчанию = source_id (или сам sid, если источника нет).
    data.setdefault("legacy_id", data.get("source_id") or sid)
    if _DRY_RUN["on"]:
        create_fn = _noop
        update_fn = _noop
        publish_fn = _noop
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
            copy_data = dict(data)
            if copy_rewrite is not None:
                copy_data = copy_rewrite(copy_data)
            create_fn(new_id, copy_data)
            publish_fn(new_id)
            _record_created(report["kind"], new_id)
            report["created"] += 1
            return
        update_fn(sid, data)
        # ПЕРЕпубликация обязательна: update_content у реестра мира переводит
        # опубликованный объект обратно в черновик (правится копия), а рантайм
        # читает только published — без этого обновлённая локация/событие/моб
        # пропадали бы из игры до ручной повторной публикации.
        publish_fn(sid)
        report["updated"] += 1
        return
    create_fn(sid, data)
    publish_fn(sid)
    _record_created(report["kind"], sid)
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
        desc = str(desc).strip()
        if not desc:
            # Источник без описания (например, seldar_city) — валидатор локаций
            # требует ≥1 описания. Подставляем название как минимальное описание,
            # чтобы не публиковать невалидный контент, и помечаем на доработку.
            desc = f"{name}."
            report["needs_check"].append({
                "id": sid, "type": "location",
                "reason": "В источнике нет описания — подставлено название. Добавьте полноценное описание локации.",
            })
        record = {
            "name": name, "type": default_type,
            "short_description": desc[:300], "description": desc,
            "imported": True, "import_source": f"data/{filename}", "source_id": str(raw_id),
        }
        _apply_record(report, sid, record, mode, get_fn=get_fn, create_fn=create_fn, update_fn=update_fn, publish_fn=publish_fn)
    return report


# --- Импорт событий локаций (ТЗ §3) -----------------------------------------
_EVENT_TYPE_MAP = {
    "trap": "trap", "battle": "met_mob", "glint": "rare_find",
    "berries": "found_resource", "alchemy_ingredient": "found_resource", "stone_or_ore": "found_resource",
}

# Спец-типы событий поиска Малого плато → типы конструктора событий.
_SP_EVENT_TYPE_MAP = {
    "reward": "rare_find", "item_reward": "rare_find", "empty_atmosphere": "found_resource",
    "curse_hint": "rare_find", "curse_or_milestone_hint": "rare_find",
    "milestone_hint": "rare_find", "seeker_hint": "rare_find", "choice_cursed_coins": "rare_find",
}


def _event_type_for(name: str) -> str:
    """Тип события по имени: ловушки/бои не теряются (например forest_trap→trap)."""
    n = str(name).lower()
    if "trap" in n:
        return "trap"
    if "battle" in n or "mob" in n:
        return "met_mob"
    if "glint" in n:
        return "rare_find"
    return _EVENT_TYPE_MAP.get(n, "found_resource")


def _event_discovery_text(event_texts: Any, ev_name: str) -> str:
    """Реальный текст обнаружения из исходных данных (event_texts[name].discovery)."""
    entry = event_texts.get(ev_name) if isinstance(event_texts, dict) else None
    if isinstance(entry, dict):
        disc = entry.get("discovery")
        if isinstance(disc, list) and disc:
            return str(disc[0])
        if isinstance(disc, str) and disc.strip():
            return disc
    return ""


def import_events(*, mode: str | None = None, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    from services import world_content_registry as wcr

    report = _rich_report("event")
    mode = _resolve_mode(mode, overwrite)
    get_fn, create_fn, update_fn, publish_fn = _wcr_funcs(wcr.KIND_EVENT, actor)

    def _copy_rewrite_event(data):
        # При копировании события привязываем его к КОПИИ локации, если та тоже
        # скопирована, иначе копия осталась бы прикреплённой к оригиналу.
        loc = str(data.get("location") or "")
        if loc and wcr.get_content(wcr.KIND_LOCATION, f"{loc}_copy") is not None:
            data["location"] = f"{loc}_copy"
        return data

    placeholder_text = False
    for filename in ("hilly_meadows.json", "ordinary_forest.json"):
        data_raw = _read_data_json(filename)
        if not isinstance(data_raw, dict):
            continue
        loc_id = safe_constructor_id(data_raw.get("id") or data_raw.get("location_id") or filename.rsplit(".", 1)[0])
        events = data_raw.get("events")
        if not isinstance(events, dict):
            continue
        event_texts = data_raw.get("event_texts") or {}
        for ev_name, chance in events.items():
            evsid = safe_constructor_id(f"{loc_id}_{ev_name}")
            if not evsid:
                report["invalid"] += 1
                continue
            try:
                ch = float(chance)
            except (TypeError, ValueError):
                ch = 0.0
            # Реальный текст обнаружения из источника; заглушка — только если его нет
            # (например, у trap/battle event_texts отсутствует).
            text = _event_discovery_text(event_texts, ev_name)
            has_real_text = bool(text)
            if not text:
                text = f"Событие локации: {ev_name}."
            record = {
                "name": str(ev_name), "type": _event_type_for(ev_name),
                "text": text, "chance": ch, "location": loc_id,
                "imported": True, "import_source": f"data/{filename}", "source_id": str(ev_name),
            }
            before = report["created"] + report["updated"]
            _apply_record(report, evsid, record, mode, get_fn=get_fn, create_fn=create_fn, update_fn=update_fn, publish_fn=publish_fn, copy_rewrite=_copy_rewrite_event)
            if report["created"] + report["updated"] > before and not has_real_text:
                placeholder_text = True

    # Малое плато: 28 событий поиска лежат отдельной list-таблицей, а не в events{}.
    sp_raw = _read_data_json("small_plateau_search_events.json")
    sp_events = sp_raw.get("events") if isinstance(sp_raw, dict) else None
    sp_imported = 0
    if isinstance(sp_events, list):
        for ev in sp_events:
            if not isinstance(ev, dict):
                report["invalid"] += 1
                continue
            ev_id = ev.get("event_id") or ev.get("id")
            evsid = safe_constructor_id(f"small_plateau_{ev_id}")
            if not evsid:
                report["invalid"] += 1
                continue
            text = str(ev.get("text") or ev.get("title") or "").strip() or f"Событие: {ev_id}"
            record = {
                "name": str(ev.get("title") or ev_id),
                "type": _SP_EVENT_TYPE_MAP.get(str(ev.get("type")), "rare_find"),
                "text": text, "result_text": str(ev.get("result_text") or ""),
                "chance": 0.0, "weight": ev.get("weight") or 0,
                "source_event_type": str(ev.get("type") or ""), "location": "small_plateau",
                "imported": True, "import_source": "data/small_plateau_search_events.json",
                "source_id": str(ev_id),
            }
            before = report["created"] + report["updated"]
            _apply_record(report, evsid, record, mode, get_fn=get_fn, create_fn=create_fn, update_fn=update_fn, publish_fn=publish_fn, copy_rewrite=_copy_rewrite_event)
            if report["created"] + report["updated"] > before:
                sp_imported += 1

    if placeholder_text:
        report["needs_check"].append({
            "id": "events", "type": "event",
            "reason": "У части событий (ловушки/бои) текст-заглушка — задайте текст/исход вручную.",
        })
    if sp_imported:
        report["needs_check"].append({
            "id": "small_plateau_events", "type": "event",
            "reason": "События поиска Малого плато импортированы со спец-типами (подсказки/проклятья/выбор монет) — проверьте сопоставление типов и исходы.",
        })
    return report


# --- Импорт узлов города (ТЗ §4) --------------------------------------------
def import_city_nodes(*, mode: str | None = None, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    from services import city_constructor_service as ccs

    report = _rich_report("city_node")
    mode = _resolve_mode(mode, overwrite)
    get_fn, create_fn, update_fn, publish_fn = _store_funcs(ccs.store(), ccs.STATUS_PUBLISHED, actor)

    def _copy_rewrite_node(data):
        # Копия квартала должна указывать на КОПИЮ города-родителя, если та есть.
        parent = str(data.get("parent_id") or "")
        if parent and get_fn(f"{parent}_copy") is not None:
            data["parent_id"] = f"{parent}_copy"
        return data

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
            }, mode, get_fn=get_fn, create_fn=create_fn, update_fn=update_fn, publish_fn=publish_fn, copy_rewrite=_copy_rewrite_node)
    return report


# --- Импорт достижений (ТЗ «импорт достижений») -----------------------------
# Существующие достижения заданы в коде/данных (small_plateau_mechanics.json +
# small_plateau_service). Структурные поля (тип/редкость/видимость/условие/
# награда) известны — задаём сид, имена/описания подтягиваем из данных.
# ВАЖНО (§5): «Проклятье? Какое проклятье?» учитывает ТОЛЬКО посмертное
# PVP-проклятье (curse_bearer_pvp_death), не от мобов/предметов/ловушек/событий/зон.
_ACHIEVEMENT_SEED = {
    "seeker": {
        "name": "Ищущий", "category": "small_plateau", "type": "exploration",
        "rarity": "legendary", "visibility": "open", "progress_type": "numeric",
        "conditions": [{"type": "discover_location", "amount": 1, "target": "small_plateau"}],
        "needs_check": "Рантайм выдаёт «Ищущего» на 1000-м поиске Малого плато (small_plateau_service.apply_search_milestone), а условие сид-определения упрощено (discover_location) — задайте счётчик из 1000 поисков. Награда «Ищущего» — доступ к seeker-контенту.",
    },
    "curse_what_curse": {
        "name": "Проклятье? Какое проклятье?", "category": "small_plateau", "type": "story",
        "rarity": "epic", "visibility": "hidden_until_earned", "progress_type": "numeric",
        "conditions": [{"type": "finish_event", "amount": 1, "target": "pvp_death_curse"}],
        "needs_check": "Условие засчитывает ТОЛЬКО посмертное PVP-проклятье (curse_bearer_pvp_death), §5 — не от мобов/предметов/ловушек/событий/зон. Логику обеспечивает small_plateau_service; награда — постоянный эффект «Носитель проклятья».",
    },
}


def import_achievements(*, mode: str | None = None, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    from services import achievement_service as ach

    report = _rich_report("achievement")
    mode = _resolve_mode(mode, overwrite)

    # Гарантируем категорию для импортированных достижений.
    cats = ach.categories()
    if cats.get("small_plateau") is None:
        try:
            cats.create("small_plateau", {"name": "Малое плато"}, actor=actor)
            cats.set_status("small_plateau", ach.STATUS_PUBLISHED, actor=actor, force=True)
        except Exception:
            pass

    # Имена/описания из данных (приоритет), структура — из сид-таблицы.
    descriptions: dict[str, dict[str, Any]] = {}
    data_raw = _read_data_json("small_plateau_mechanics.json")
    if isinstance(data_raw, dict) and isinstance(data_raw.get("achievements"), list):
        for entry in data_raw["achievements"]:
            if isinstance(entry, dict):
                aid = str(entry.get("achievement_id") or entry.get("id") or "").strip()
                if aid:
                    descriptions[aid] = entry

    get_fn, create_fn, update_fn, publish_fn = _store_funcs(ach.store(), ach.STATUS_PUBLISHED, actor)
    for aid, seed in _ACHIEVEMENT_SEED.items():
        src = descriptions.get(aid, {})
        name = src.get("name") or seed["name"]
        desc = src.get("description") or ""
        # Редкость — из живого источника (small_plateau_mechanics.json), если есть:
        # там curse_what_curse помечен legendary, а сид по ошибке хранил epic, из-за
        # чего конструктор расходился с рантаймовым достижением игрока.
        rarity = src.get("rarity") or seed["rarity"]
        record = {
            "name": name, "short_description": desc[:300], "description": desc,
            "category": seed["category"], "type": seed["type"], "rarity": rarity,
            "visibility": seed["visibility"], "progress_type": seed["progress_type"],
            "condition_logic": "all", "conditions": seed["conditions"], "rewards": [],
            "notify_message": {"format": "single", "text": f"Получено достижение: «{name}»."},
            "imported": True, "import_source": "achievement_seed", "source_id": aid,
        }
        before = report["created"] + report["updated"]
        _apply_record(report, aid, record, mode, get_fn=get_fn, create_fn=create_fn, update_fn=update_fn, publish_fn=publish_fn)
        if report["created"] + report["updated"] > before and seed.get("needs_check"):
            report["needs_check"].append({"id": aid, "type": "achievement", "reason": seed["needs_check"]})
    return report


# --- Импорт штрафов (ТЗ «импорт штрафов») -----------------------------------
# Существующие ТИПЫ штрафов заданы в коде (fine_service: облавы Чёрного рынка/
# Крота/казино, базовая сумма 100). Заводим их как опубликованные шаблоны в
# Конструкторе штрафов. Активные штрафы игроков — отдельный рантайм (fine_service),
# уже отображаются в карточке игрока/профиле.
# (id, название, тип, источник, базовая сумма, ограничения)
_FINE_SEED = [
    ("city_fine", "Городской штраф", "city", "guard_decision", 100, ["force_fortress", "block_city"]),
    ("black_market_raid_fine", "Штраф за облаву на Чёрном рынке", "raid", "black_market_raid", 100, ["force_fortress", "block_city"]),
    ("informer_raid_fine", "Штраф за облаву у информатора Крота", "raid", "informer_raid", 100, ["force_fortress", "block_city"]),
    ("casino_raid_fine", "Штраф за облаву в подпольном казино", "raid", "casino_raid", 100, ["force_fortress", "block_city"]),
    ("chat_rules_fine", "Штраф за нарушение правил чата", "chat_rules", "chat_violation", 100, ["block_chat"]),
    ("manual_fine", "Ручной штраф администратора", "manual", "admin_decision", 100, []),
]


def import_fines(*, mode: str | None = None, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    from services import fine_constructor_service as fc

    report = _rich_report("fine_def")
    mode = _resolve_mode(mode, overwrite)
    get_fn, create_fn, update_fn, publish_fn = _store_funcs(fc.store(), fc.STATUS_PUBLISHED, actor)
    for fid, name, ftype, source, base, restrictions in _FINE_SEED:
        record = {
            "name": name, "type": ftype, "source": source, "currency": "copper",
            "base_amount": base, "first_deadline_days": 7, "second_deadline_days": 23,
            "restriction_start_day": 24, "interest_enabled": True, "interest_percent_per_day": 1,
            "interest_start_day": 8, "restrictions": [{"code": c} for c in restrictions],
            "issuer_roles": ["guard", "manager", "admin"],
            "messages": {
                "on_issue": "Вам выписан штраф.", "on_pay": "Штраф оплачен.",
                "on_block": "Доступ закрыт до оплаты штрафа.",
            },
            "imported": True, "import_source": "fine_seed", "source_id": fid,
        }
        _apply_record(report, fid, record, mode, get_fn=get_fn, create_fn=create_fn, update_fn=update_fn, publish_fn=publish_fn)
    report["needs_check"].append({
        "id": "fines", "type": "fine_def",
        "reason": "Суммы/сроки/проценты — типовые значения; уточните под каждую облаву. Оплата у Управляющего города/крепости и снятие в админке работают через fine_service.",
    })
    return report


# --- Импорт рецептов ремесла (ТЗ «импорт ремесла») --------------------------
def import_recipes(*, mode: str | None = None, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    from services import recipe_constructor_service as rcs

    report = _rich_report("recipe")
    mode = _resolve_mode(mode, overwrite)
    get_fn, create_fn, update_fn, publish_fn = _store_funcs(rcs.store(), rcs.STATUS_PUBLISHED, actor)
    data_raw = _read_data_json("crafting_recipes.json")
    if not isinstance(data_raw, list):
        report["errors"].append({"id": "crafting_recipes.json", "type": "recipe", "reason": "Файл рецептов отсутствует или повреждён."})
        return report
    for raw in data_raw:
        if not isinstance(raw, dict):
            report["invalid"] += 1
            continue
        sid = safe_constructor_id(raw.get("id"))
        if not sid:
            report["invalid"] += 1
            report["errors"].append({"id": str(raw.get("id")), "type": "recipe", "reason": "Не удалось получить корректный id."})
            continue
        output = raw.get("output") if isinstance(raw.get("output"), dict) else {}
        ingredients = [
            {"item_id": str(ing.get("item_id") or ""), "amount": ing.get("amount") or 1}
            for ing in (raw.get("ingredients") or []) if isinstance(ing, dict) and ing.get("item_id")
        ]
        record = {
            "name": (output.get("name") or raw.get("description") or sid),
            "workshop": str(raw.get("workshop") or ""),
            "section": str(raw.get("section") or ""),
            "description": str(raw.get("description") or ""),
            "output_item_id": str(output.get("item_id") or ""),
            "output_amount": output.get("amount") or 1,
            "ingredients": ingredients,
            "craft_time": raw.get("craft_time_seconds") or 0,
            "success_chance": 100, "quality_chance": 0, "fail_chance": 0,
            "actions": list(raw.get("actions") or []),
            "blueprint_required": False, "hidden": False,
            "imported": True, "import_source": "data/crafting_recipes.json", "source_id": str(raw.get("id")),
        }
        _apply_record(report, sid, record, mode, get_fn=get_fn, create_fn=create_fn, update_fn=update_fn, publish_fn=publish_fn)
    return report


# --- Импорт раскладки профиля (ТЗ «импорт профиля») -------------------------
# Текущая раскладка профиля задана во фронте (вкладки Персонаж/Инвентарь/Навыки/
# Журнал/Сервисы; вкладки «Обзор» НЕТ — §1.4). Заводим её в Конструктор раскладки
# профиля, чтобы админ мог открыть/править/переставлять. Ключи вкладок совпадают
# с рендером профиля (character/inventory/skills/info/services).
_PROFILE_TAB_SEED = [
    ("character", "Персонаж", "🧙", 1),
    ("inventory", "Инвентарь", "🎒", 2),
    ("skills", "Навыки", "✨", 3),
    ("info", "Журнал", "📜", 4),
    ("services", "Сервисы", "🤝", 5),
]
# (id, название, тип блока, вкладка, порядок) — распределение данных «Обзора» (§1.4).
_PROFILE_BLOCK_SEED = [
    ("blk_main_info", "Основные данные", "main_info", "character", 1),
    ("blk_resources", "HP/мана/дух/энергия", "resources", "character", 2),
    ("blk_stats", "Характеристики", "stats", "character", 3),
    ("blk_equipment", "Экипировка", "equipment", "character", 4),
    ("blk_effects", "Эффекты", "effects", "character", 5),
    ("blk_warnings", "Предупреждения", "warnings", "character", 6),
    ("blk_inventory", "Инвентарь", "inventory", "inventory", 1),
    ("blk_skills", "Навыки", "skills", "skills", 1),
    ("blk_passive_skills", "Пассивные навыки", "passive_skills", "skills", 2),
    ("blk_activity", "Активность", "activity", "info", 1),
    ("blk_fines", "Штрафы", "fines", "info", 2),
    ("blk_currency", "Валюта", "currency", "info", 3),
    ("blk_services", "Сервисы", "services", "services", 1),
    ("blk_transfer", "Передача предметов", "transfer", "services", 2),
    ("blk_danger", "Опасная зона", "danger_zone", "character", 7),
]


def import_profile_layout(*, mode: str | None = None, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    from services import profile_layout_service as pls

    report = _rich_report("profile_layout")
    mode = _resolve_mode(mode, overwrite)
    get_fn, create_fn, update_fn, publish_fn = _store_funcs(pls.store(), pls.STATUS_PUBLISHED, actor)
    for tab_key, label, icon, order in _PROFILE_TAB_SEED:
        _apply_record(report, f"tab_{tab_key}", {
            "_kind": pls.KIND_TAB, "label": label, "tab_key": tab_key, "icon": icon,
            "order": order, "visibility": "always", "default_tab": tab_key == "character",
            "imported": True, "import_source": "profile_layout_seed", "source_id": tab_key,
        }, mode, get_fn=get_fn, create_fn=create_fn, update_fn=update_fn, publish_fn=publish_fn)
    for bid, name, block_type, tab, order in _PROFILE_BLOCK_SEED:
        _apply_record(report, bid, {
            "_kind": pls.KIND_BLOCK, "name": name, "block_type": block_type, "tab": tab,
            "order": order, "visibility": "always",
            "imported": True, "import_source": "profile_layout_seed", "source_id": bid,
        }, mode, get_fn=get_fn, create_fn=create_fn, update_fn=update_fn, publish_fn=publish_fn)
    report["needs_check"].append({
        "id": "overview", "type": "profile_layout",
        "reason": "Вкладка «Обзор» не переносится как отдельная (§1.4) — её данные распределены по Персонаж/Журнал/Сервисы. Проверьте порядок/видимость и при необходимости добавьте оформление (profile_theme).",
    })
    return report


# --- Импорт лагерей (доп. ТЗ §4) --------------------------------------------
def import_camps(*, mode: str | None = None, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    """Импорт существующих лагерей в конструктор лагеря.

    Отдельного статического JSON лагерей в проекте нет — механика отдыха/готовки
    живёт в external_location_service. Поэтому сид пуст: возвращаем отчёт с
    needs_check, чтобы админ завёл лагеря вручную (а не молча «успешно ноль»)."""
    report = _rich_report("camp")
    report["needs_check"].append({
        "id": "camps", "type": "camp",
        "reason": "Статического источника лагерей нет (отдых/готовка заданы в коде локаций). Создайте лагеря вручную в конструкторе и привяжите к локациям.",
    })
    return report


# --- Импорт черт/благословений/фаз (ТЗ «черты/благословения/фазы») ----------
# (id, название, ранг, триггер, описание-для-игрока)
_TRAIT_SEED = [
    ("tough_hide", "Крепкая шкура", "special", "passive", "Моб получает меньше физического урона."),
    ("dense_shell", "Плотная оболочка", "special", "on_receive_damage", "Доп. защита от первого сильного удара."),
    ("quick_reaction", "Быстрая реакция", "special", "passive", "Чаще уклоняется или снижает шанс попадания по себе."),
    ("sharp_claws", "Острые когти", "special", "on_attack", "Атаки с шансом вызывают кровотечение."),
    ("acid_spit", "Едкая слюна", "special", "on_attack", "Атака может немного снизить защиту цели."),
    ("weak_venom_body", "Слабое ядовитое тело", "special", "on_receive_damage", "Атакующий в ближнем бою может получить слабое отравление."),
    ("heavy_body", "Тяжёлое тело", "special", "passive", "Бонус к сопротивлению оглушению и отталкиванию."),
    ("night_hunt", "Ночная охота", "special", "passive", "В тьме/ночью/подземелье — бонус к точности и урону."),
    ("territorial_rage", "Территориальная ярость", "special", "passive", "Сильнее в своей основной локации."),
    ("fearsome_visage", "Пугающий вид", "special", "battle_start", "В начале боя снижает точность/крит игрока."),
    ("ragged_strike", "Рваный удар", "special", "on_attack", "Атака с шансом накладывает лёгкую травму/кровотечение."),
    ("element_resist", "Сопротивление стихии", "special", "passive", "Меньше урона от выбранной стихии или зоны."),
    ("unstable_flesh", "Нестабильная плоть", "special", "on_receive_damage", "При получении урона с шансом случайный слабый баф/дебаф."),
    ("survival_instinct", "Инстинкт выживания", "special", "passive", "При низком HP бонус к уклонению/побегу."),
    ("unpleasant_prey", "Неприятная добыча", "special", "on_death", "Риск слабого негативного эффекта при сборе добычи."),
    ("enhanced_regen", "Усиленная регенерация", "elite", "on_turn_start", "Восстанавливает здоровье каждый ход."),
    ("combat_adaptation", "Боевая адаптация", "elite", "on_receive_damage", "После ударов одного типа — временное сопротивление этому типу."),
    ("riposte", "Ответный выпад", "elite", "on_receive_damage", "После прямого удара с шансом отвечает атакой."),
    ("elite_pressure", "Давление элиты", "elite", "passive", "Пока жив, игрок получает штраф к точности/уклонению."),
    ("armor_pierce", "Бронебойные удары", "elite", "on_attack", "Атаки частично игнорируют физзащиту игрока."),
    ("disrupting_strike", "Срывающий удар", "elite", "on_attack", "Атака может временно заблокировать доп. действие игрока."),
    ("hunter_threat", "Угроза охотника", "elite", "on_attack", "Выбирает ослабленную цель и бьёт сильнее."),
    ("healing_suppression", "Подавление лечения", "elite", "passive", "Пока жив, лечение игрока/группы слабее."),
    ("unstable_field", "Нестабильное поле", "elite", "on_turn_start", "Каждые N ходов на поле появляется случайный слабый эффект."),
    ("wound_empowerment", "Усиление от ранения", "elite", "passive", "Чем меньше HP, тем сильнее атаки."),
    ("defensive_phase", "Защитная фаза", "elite", "phase_change", "При низком HP временно усиливает защиту."),
    ("summon_weak_minions", "Призыв слабых помощников", "elite", "on_turn_start", "Призывает слабых помощников через интервалы."),
    ("threat_aura", "Аура угрозы", "elite", "passive", "Снижает боевую эффективность игроков вокруг."),
    ("strong_natural_defense", "Сильная природная защита", "elite", "passive", "Заметная защита от выбранных эффектов (яд/кровь/огонь/контроль)."),
    ("defense_breaker", "Разрушитель защиты", "elite", "on_attack", "Атаки могут временно снижать защиту игрока."),
    ("unique_defense", "Уникальная защита", "unique", "passive", "Особая защита, меняющая тактику боя."),
    ("unique_attack", "Уникальная атака", "unique", "on_attack", "Особая усиленная атака с откатом/условием."),
    ("shifting_defense", "Меняющаяся защита", "unique", "on_turn_start", "Тип защиты меняется каждые N ходов."),
    ("mirror_carapace", "Зеркальный панцирь", "unique", "on_receive_damage", "Часть магического урона отражается (без цепочек)."),
    ("unbreakable_stance", "Непробиваемая стойка", "unique", "phase_change", "Резко снижает входящий физурон, пока стойка активна."),
    ("cursed_presence", "Проклятое присутствие", "unique", "on_turn_start", "Шанс наложить/усилить слабое проклятье."),
    ("space_rift", "Разлом пространства", "unique", "on_turn_start", "Искажает бой: цель/точность/стоимость/позиция."),
    ("resource_devour", "Пожирание ресурса", "unique", "on_attack", "Забирает ману/Дух/энергию при атаке."),
    ("phase_invulnerability", "Фазовая неуязвимость", "unique", "phase_change", "Периодически почти неуязвим до конца фазы."),
    ("legendary_rage", "Легендарная ярость", "unique", "phase_change", "При низком HP больше урона/навыков, но больше входящего урона."),
    ("world_pressure", "Давление мирового существа", "world", "passive", "Пока жив, все участники получают штраф к точности/уклонению/восстановлению."),
    ("region_quake", "Сотрясение региона", "world", "on_turn_start", "Каждые N ходов региональный удар по всем участникам."),
    ("world_suppression_aura", "Мировая аура подавления", "world", "passive", "Ослабляет лечение/очищение/благословения во всём бою."),
    ("formation_break", "Разрушение строя", "world", "passive", "Снижает эффективность групповых аур и построений."),
    ("world_devour", "Поглощение мира", "world", "on_turn_start", "Периодически поглощает ману/Дух/энергию игроков."),
    ("minion_call", "Зов прислужников", "world", "on_turn_start", "Призывает волны помощников по фазе/таймеру."),
    ("unstable_reality", "Нестабильная реальность", "world", "on_turn_start", "Периодически меняет правила боя."),
    ("inexhaustible_body", "Неистощимое тело", "world", "on_turn_start", "Восстанавливает HP, если урона давно не было достаточно."),
    ("catastrophic_limit", "Катастрофический предел", "world", "on_turn_start", "При затяжном бое усиливается по таймеру (soft-enrage)."),
    ("world_loot", "Мировая добыча", "world", "on_death", "Награда зависит от вклада/стадии/участия в фазах."),
]

# (id, название, источник, описание)
_BLESSING_SEED = [
    ("blessing_strength", "Благословение силы", "item", "Повышает Силу и физический урон."),
    ("blessing_endurance", "Благословение выносливости", "item", "Повышает Выносливость и максимум HP."),
    ("blessing_wisdom", "Благословение мудрости", "zone", "Усиливает лечение, очищение и защитные действия."),
    ("blessing_intellect", "Благословение интеллекта", "zone", "Усиливает навыки Маны и магические эффекты."),
    ("blessing_combat_spirit", "Благословение боевого Духа", "item", "Усиливает ресурс Дух, физнавыки, стойки и приёмы."),
    ("blessing_hunter", "Благословение охотника", "event", "Повышает шанс добычи с животных, следов и охотничьих событий."),
    ("blessing_herbalist", "Благословение травника", "zone", "Повышает шанс найти травы и алхимические ингредиенты."),
    ("blessing_miner", "Благословение рудокопа", "zone", "Повышает шанс найти руду, камень или материал."),
    ("blessing_craftsman", "Благословение ремесленника", "event", "Повышает шанс успеха/качества ремесла."),
    ("blessing_merchant", "Благословение купца", "event", "Улучшает покупку/продажу или снижает комиссию."),
    ("blessing_wanderer", "Благословение странника", "zone", "Снижает расход энергии или повышает мирные события."),
    ("blessing_protection", "Благословение защиты", "item", "Снижает входящий урон."),
    ("blessing_cleanse", "Благословение очищения", "zone", "Повышает шанс снять негатив или ослабляет проклятья."),
    ("blessing_luck", "Благословение удачи", "event", "Повышает шанс получить дополнительную/редкую награду."),
    ("blessing_experience", "Благословение опыта", "event", "Увеличивает получаемый опыт."),
    ("blessing_coins", "Благословение монет", "event", "Увеличивает получаемые монеты из разрешённых источников."),
    ("blessing_event", "Благословение события", "event", "Усиливает игрока/мобов в рамках определённого события."),
    ("blessing_victor", "Благословение победителя", "boss_phase", "Временный бонус после сложной победы над боссом."),
    ("blessing_risk", "Благословение риска", "event", "Больше наград, но бой/поиск становится опаснее."),
]

# (id, название, тип триггера, описание)
_PHASE_SEED = [
    ("phase_intro", "Вступительная фаза", "manual", "Начальная фаза боя: базовый набор навыков, показ главной механики."),
    ("phase_defense_check", "Фаза проверки защиты", "hp_percent", "Сильные удары — проверка физ/маг защиты игроков."),
    ("phase_pressure", "Фаза давления", "turn_count", "Чаще атакует, сокращает безопасные окна восстановления."),
    ("phase_summon", "Фаза призыва", "turn_count", "Призывает помощников или волны врагов."),
    ("phase_shell", "Фаза защитного панциря", "hp_percent", "Сильная защита, пока не кончится фаза или условие."),
    ("phase_vulnerable", "Уязвимая фаза", "objective", "После условия временно получает больше урона."),
    ("phase_rage", "Фаза ярости", "hp_percent", "При низком HP больше урона и чаще активные навыки."),
    ("phase_drain", "Фаза истощения игроков", "hp_percent", "Активно снижает ресурсы игроков (мана/Дух/энергия)."),
    ("phase_field_control", "Фаза контроля поля", "turn_count", "Эффекты зоны: туман/огонь/мороз/тьма/ловушки."),
    ("phase_hunt_weak", "Фаза охоты на слабых", "objective", "Чаще выбирает игроков с низким HP или дебафами."),
    ("phase_reflection", "Фаза отражения", "hp_percent", "Часть урона возвращается атакующим."),
    ("phase_no_heal", "Фаза запрета восстановления", "hp_percent", "Ослабляет лечение/регенерацию/очищение."),
    ("phase_rift", "Фаза разлома", "turn_count", "Искажает порядок действий/цели/стоимость/позиции."),
    ("phase_charge", "Фаза накопления силы", "turn_count", "Накопление заряда → сильная атака, если не прервать."),
    ("phase_armor_decay", "Фаза распада брони", "hp_percent", "Теряет защиту, но наносит больше урона."),
    ("phase_recovery", "Фаза восстановления", "hp_percent", "Пытается восстановить HP или снять негатив."),
    ("phase_damage_check", "Фаза испытания урона", "turn_count", "Нужно нанести достаточно урона за N ходов, иначе усиление."),
    ("phase_survival_check", "Фаза испытания выживания", "turn_count", "Усиливает давление; задача игроков — пережить фазу."),
    ("phase_final", "Финальная фаза", "hp_percent", "Последняя опасная фаза, самые сильные навыки."),
    ("phase_post_death", "Посмертная фаза", "manual", "После смерти: взрыв/проклятье/волна/зона/событие."),
]


def import_traits(*, mode: str | None = None, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    from services import trait_constructor_service as tcs

    report = _rich_report("trait")
    mode = _resolve_mode(mode, overwrite)
    get_fn, create_fn, update_fn, publish_fn = _store_funcs(tcs.store(), tcs.STATUS_PUBLISHED, actor)
    for tid, name, rank, trigger, desc in _TRAIT_SEED:
        record = {
            "trait_name": name, "trait_rank": rank, "trigger": trigger,
            "player_text": desc, "admin_description": desc,
            "stack_rule": "strongest_only", "applicable_mob_categories": [],
            "can_be_removed": False,
            "imported": True, "import_source": "trait_seed", "source_id": tid,
        }
        _apply_record(report, tid, record, mode, get_fn=get_fn, create_fn=create_fn, update_fn=update_fn, publish_fn=publish_fn)
    return report


def import_blessings(*, mode: str | None = None, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    from services import blessing_constructor_service as bcs

    report = _rich_report("blessing")
    mode = _resolve_mode(mode, overwrite)
    get_fn, create_fn, update_fn, publish_fn = _store_funcs(bcs.store(), bcs.STATUS_PUBLISHED, actor)
    for bid, name, source, desc in _BLESSING_SEED:
        record = {
            "blessing_name": name, "source_type": source, "allowed_targets": ["player"],
            "player_text": desc, "bonus_values": {"flat_bonus": 0, "percent_bonus": 0, "duration_seconds": 0},
            "stack_rule": "refresh", "show_to_player": True,
            "imported": True, "import_source": "blessing_seed", "source_id": bid,
        }
        _apply_record(report, bid, record, mode, get_fn=get_fn, create_fn=create_fn, update_fn=update_fn, publish_fn=publish_fn)
    return report


def import_phases(*, mode: str | None = None, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    from services import phase_constructor_service as pcs

    report = _rich_report("phase")
    mode = _resolve_mode(mode, overwrite)
    get_fn, create_fn, update_fn, publish_fn = _store_funcs(pcs.store(), pcs.STATUS_PUBLISHED, actor)
    all_ranks = list(pcs.BOSS_RANKS)
    for pid, name, trigger, desc in _PHASE_SEED:
        record = {
            "phase_name": name, "trigger_type": trigger, "trigger_value": 0,
            "allowed_boss_ranks": all_ranks, "phase_text_for_player": desc,
            "phase_admin_notes": desc, "phase_effects": [], "phase_skill_pool": [],
            "imported": True, "import_source": "phase_seed", "source_id": pid,
        }
        _apply_record(report, pid, record, mode, get_fn=get_fn, create_fn=create_fn, update_fn=update_fn, publish_fn=publish_fn)
    return report


# --- Импорт рас (чат-ТЗ «уровни/опыт/регистрация/расы») ---------------------
def import_races(*, mode: str | None = None, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    from services import race_constructor_service as rcs

    report = _rich_report("race")
    mode = _resolve_mode(mode, overwrite)
    data_raw = _read_data_json("races.json")
    if not isinstance(data_raw, dict) or not data_raw:
        report["errors"].append({"id": "races.json", "type": "race", "reason": "Файл рас отсутствует или повреждён."})
        return report
    get_fn, create_fn, update_fn, publish_fn = _store_funcs(rcs.store(), rcs.STATUS_PUBLISHED, actor)
    for raw_id, race in data_raw.items():
        sid = safe_constructor_id(raw_id)
        if not sid or not isinstance(race, dict):
            report["invalid"] += 1
            continue
        record = {
            "race_name": race.get("name") or sid,
            "description": str(race.get("description") or ""),
            "stat_bonuses": race.get("bonuses") if isinstance(race.get("bonuses"), dict) else {},
            "starting_stats": race.get("stats") if isinstance(race.get("stats"), dict) else {},
            "playable": True,
            "imported": True, "import_source": "data/races.json", "source_id": str(raw_id),
        }
        _apply_record(report, sid, record, mode, get_fn=get_fn, create_fn=create_fn, update_fn=update_fn, publish_fn=publish_fn)
    return report


# --- Импорт репутаций (full-import ТЗ §5.17) --------------------------------
# Репутации заданы в коде/механиках (стража, торговцы, ремесленники, Чёрный
# рынок, информатор Крот, гильдия, арена). Заводим их как опубликованные
# определения, чтобы админ мог править пороги/эффекты/тексты. Скрытые репутации
# (crime/informer) не показывают игроку точное значение (§6.2).
# (id, название, видимость, область, режим отображения)
_REPUTATION_SEED = [
    ("rep_seldar_city", "Репутация Селдара", "visible", "city", "stage"),
    ("rep_city_guards", "Репутация у городской стражи", "visible", "guards", "stage"),
    ("rep_traders", "Репутация у торговцев", "visible", "traders", "stage"),
    ("rep_crafters", "Репутация у ремесленников", "visible", "crafters", "stage"),
    ("rep_black_market", "Репутация на Чёрном рынке", "hidden", "crime_group", "stage"),
    ("rep_informer_mole", "Доверие информатора Крота", "hidden", "npc", "stage"),
    ("rep_guild", "Репутация в гильдии", "visible", "guild", "stage"),
    ("rep_arena", "Репутация на арене (PvP)", "visible", "world_event", "stage"),
]


def import_reputation(*, mode: str | None = None, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    from services import reputation_constructor_service as rep

    report = _rich_report("reputation")
    mode = _resolve_mode(mode, overwrite)
    get_fn, create_fn, update_fn, publish_fn = _store_funcs(rep.store(), rep.STATUS_PUBLISHED, actor)
    for rid, name, visibility, scope, display in _REPUTATION_SEED:
        hidden = visibility == "hidden"
        record = {
            "name_ru": name, "visibility": visibility, "scope_type": scope,
            "display_mode": display, "min_value": -1000, "max_value": 1000,
            "default_value": 0, "show_to_player": True,
            "show_exact_value": not hidden,
            "description_player": name, "description_admin": name,
            "imported": True, "import_source": "reputation_seed", "source_id": rid,
        }
        _apply_record(report, rid, record, mode, get_fn=get_fn, create_fn=create_fn, update_fn=update_fn, publish_fn=publish_fn)
    report["needs_check"].append({
        "id": "reputation", "type": "reputation",
        "reason": "Диапазоны/стадии/правила изменения — типовые; уточните пороги и последствия под каждую фракцию. Рантайм-применение репутации — на вырост.",
    })
    return report


# --- Импорт товаров рынка (full-import ТЗ §5.15) ----------------------------
def import_shops(*, mode: str | None = None, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    """Товары рынка Селдара (data/seldar_market.json) → city_shop_item."""
    from services import city_constructor_service as ccs

    report = _rich_report("city_shop_item")
    mode = _resolve_mode(mode, overwrite)
    get_fn, create_fn, update_fn, publish_fn = _store_funcs(ccs.store(), ccs.STATUS_PUBLISHED, actor)
    data_raw = _read_data_json("seldar_market.json")
    items = data_raw.get("items") if isinstance(data_raw, dict) else None
    if not isinstance(items, list):
        report["errors"].append({"id": "seldar_market.json", "type": "city_shop_item", "reason": "Файл рынка отсутствует или повреждён."})
        return report
    currency = str((data_raw or {}).get("currency") or "copper")
    if currency not in ccs.CURRENCIES:
        currency = "copper"
    for raw in items:
        if not isinstance(raw, dict):
            report["invalid"] += 1
            continue
        item_id = str(raw.get("item_id") or "").strip()
        sid = safe_constructor_id(f"market_{item_id}")
        if not item_id or not sid:
            report["invalid"] += 1
            continue
        record = {
            "_kind": ccs.KIND_SHOP_ITEM,
            "item_id": item_id,
            "display_name": str(raw.get("display_name") or item_id),
            "shop_kind": "trade_quarter", "node_id": "trade_quarter",
            "currency": currency, "price_buy": raw.get("buy_price_copper") or 0,
            "can_buy": True, "can_sell": False, "stock_type": "always",
            "category": str(raw.get("category") or ""),
            "description": str(raw.get("description") or ""),
            "imported": True, "import_source": "data/seldar_market.json", "source_id": item_id,
        }
        _apply_record(report, sid, record, mode, get_fn=get_fn, create_fn=create_fn, update_fn=update_fn, publish_fn=publish_fn)
    report["needs_check"].append({
        "id": "shops", "type": "city_shop_item",
        "reason": "Товары привязаны к узлу «trade_quarter» с продажей за медь; проверьте привязку к узлу города, цены продажи и лимиты/ротацию.",
    })
    return report


# --- Импорт текстов бота (full-import ТЗ §5.18) -----------------------------
# Тексты бота разбросаны по коду хендлеров/сервисов. Сид заводит ключевые
# сообщения (системные/ошибки/бой/штрафы/доставка/награды/смерть/проклятия) как
# опубликованные редактируемые записи. Якорные тексты (поиск §5.10, дар §5.19)
# перенесены дословно. Рантайм-чтение игрой — text_runtime под use_v2_texts.
# (text_key, текст, контекст, платформа, [переменные])
_TEXT_SEED = [
    ("system.welcome", "Добро пожаловать в Нер-Талис!", "system", "both", []),
    ("system.help", "Используйте кнопки меню, чтобы играть.", "system", "both", []),
    ("error.not_enough_energy", "Недостаточно энергии для этого действия.", "error", "both", []),
    ("error.in_battle", "Сейчас вы в бою — действие недоступно.", "error", "both", []),
    ("error.move_blocked", "Сейчас вы не можете перемещаться.", "error", "both", []),
    ("error.inventory_full", "Инвентарь переполнен.", "error", "both", []),
    ("search.nothing_found", "Вы ничего не нашли — похоже, на этой локации уже всё забрали.", "search", "both", []),
    ("battle.victory", "Победа! Вы одолели противника.", "battle", "both", []),
    ("battle.defeat", "Поражение. Вы потерпели неудачу в бою.", "battle", "both", []),
    ("craft.success", "Изделие готово.", "craft", "both", []),
    ("craft.fail", "Что-то пошло не так — изделие испорчено.", "craft", "both", []),
    ("fine.issued", "Вам выписан штраф.", "fine", "both", []),
    ("fine.paid", "Штраф оплачен.", "fine", "both", []),
    ("fine.blocked", "Доступ закрыт до оплаты штрафа.", "fine", "both", []),
    ("delivery.admin_gift", "Вы получили в дар от высших сил: {items}", "delivery", "both", ["items"]),
    ("reward.received", "Вы получили награду: {reward}", "reward", "both", ["reward"]),
    ("promo.redeemed", "Промокод активирован: {reward}", "promo", "both", ["reward"]),
    ("death.generic", "Вы погибли. Придётся восстановиться.", "death", "both", []),
    ("curse.applied", "На вас наложено проклятье: {curse}", "curse", "both", ["curse"]),
    ("achievement.earned", "Получено достижение: «{name}».", "achievement", "both", ["name"]),
    ("transition.moved", "Вы переходите: {destination}", "transition", "both", ["destination"]),
    ("camp.rest_done", "Отдых завершён. Силы восстановлены.", "camp", "both", []),
]


def import_texts(*, mode: str | None = None, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    from services import text_constructor_service as tcs

    report = _rich_report("text")
    mode = _resolve_mode(mode, overwrite)
    get_fn, create_fn, update_fn, publish_fn = _store_funcs(tcs.store(), tcs.STATUS_PUBLISHED, actor)
    for key, value, context, platform, variables in _TEXT_SEED:
        sid = safe_constructor_id(key)
        if not sid:
            report["invalid"] += 1
            continue
        record = {
            "text_key": key, "text_value": value, "context": context,
            "platform": platform, "parse_mode": "none",
            "variables": list(variables), "fallback_text": value,
            "entity_type": "none", "entity_id": "",
            "imported": True, "import_source": "text_seed", "source_id": key,
        }
        _apply_record(report, sid, record, mode, get_fn=get_fn, create_fn=create_fn, update_fn=update_fn, publish_fn=publish_fn)
    report["needs_check"].append({
        "id": "texts", "type": "text",
        "reason": "Импортирован базовый набор текстов; большинство сообщений бота всё ещё в коде. Добавьте недостающие ключи и включите чтение через feature flag use_v2_texts.",
    })
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
    "achievement": import_achievements, "fine_def": import_fines, "recipe": import_recipes,
    "profile_layout": import_profile_layout, "camp": import_camps,
    "trait": import_traits, "blessing": import_blessings, "phase": import_phases,
    "race": import_races, "reputation": import_reputation, "shop": import_shops,
    "text": import_texts,
}


def import_all(kinds: list[str] | None = None, *, overwrite: bool = False, mode: str | None = None, actor: str = "import", dry_run: bool = False) -> dict[str, Any]:
    selected = [k for k in (kinds or list(IMPORTERS)) if k in IMPORTERS]
    _BATCH.clear()
    with _dry_run_scope(dry_run):
        reports = [_normalize_report(IMPORTERS[k](overwrite=overwrite, mode=mode, actor=actor)) for k in selected]
    # Журнал созданных записей — только для реального импорта (ТЗ §4.1, откат).
    if not dry_run:
        try:
            save_import_journal(list(_BATCH))
        except Exception:
            pass
    summary = {
        "found": sum(r["found"] for r in reports),
        "created": sum(r["created"] for r in reports),
        "updated": sum(r["updated"] for r in reports),
        "skipped": sum(r["skipped"] for r in reports),
        "invalid": sum(r["invalid"] for r in reports),
        "errors": sum(len(r["errors"]) for r in reports),
        "needs_check": sum(len(r["needs_check"]) for r in reports),
        "mode": _resolve_mode(mode, overwrite),
        "dry_run": bool(dry_run),
        "kinds": selected,
    }
    result = {"ok": True, "dry_run": bool(dry_run), "reports": reports, "summary": summary}
    # Сохраняем отчёт последнего запуска (ТЗ §10, AC#13) — и для dry-run, и для
    # реального импорта; в админке его можно открыть в JSON или markdown.
    try:
        save_last_report(result)
    except Exception:
        pass
    return result


# --- Отчёт импорта (ТЗ §10): сохранение последнего + markdown ----------------
def _report_path():
    import os
    from project_paths import project_path

    override = os.environ.get("IMPORT_REPORT_PATH")
    if override:
        from pathlib import Path

        return Path(override)
    return project_path("data", "import_report.json")


def save_last_report(result: dict[str, Any]) -> None:
    import json

    path = _report_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    with path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)


def load_last_report() -> dict[str, Any] | None:
    import json

    path = _report_path()
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def build_import_markdown(result: dict[str, Any] | None) -> str:
    """Markdown-отчёт последнего импорта (ТЗ §10)."""
    if not result:
        return "# Отчёт импорта\n\nОтчётов пока нет — запустите импорт или dry-run."
    summary = result.get("summary") or {}
    lines: list[str] = []
    title = "Отчёт импорта (dry-run)" if result.get("dry_run") else "Отчёт импорта"
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- Режим: **{summary.get('mode', '—')}**")
    lines.append(f"- Найдено: **{summary.get('found', 0)}**")
    lines.append(f"- Создано: **{summary.get('created', 0)}**")
    lines.append(f"- Обновлено: **{summary.get('updated', 0)}**")
    lines.append(f"- Пропущено: **{summary.get('skipped', 0)}**")
    lines.append(f"- Некорректных: **{summary.get('invalid', 0)}**")
    lines.append(f"- Ошибок: **{summary.get('errors', 0)}**")
    lines.append(f"- Требует проверки: **{summary.get('needs_check', 0)}**")
    lines.append("")
    lines.append("| Тип | Найдено | Создано | Обновлено | Пропущено | Некорр. | Ошибки | Проверить |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in result.get("reports") or []:
        lines.append(
            f"| {r.get('kind', '—')} | {r.get('found', 0)} | {r.get('created', 0)} | "
            f"{r.get('updated', 0)} | {r.get('skipped', 0)} | {r.get('invalid', 0)} | "
            f"{len(r.get('errors') or [])} | {len(r.get('needs_check') or [])} |"
        )
    # Подробности «требует проверки» и ошибок.
    checks = [(r.get("kind"), nc) for r in (result.get("reports") or []) for nc in (r.get("needs_check") or [])]
    if checks:
        lines.append("")
        lines.append("## Требует ручной проверки")
        for kind, nc in checks:
            reason = nc.get("reason") if isinstance(nc, dict) else str(nc)
            ident = nc.get("id") if isinstance(nc, dict) else ""
            lines.append(f"- **{kind}/{ident}**: {reason}")
    errors = [(r.get("kind"), er) for r in (result.get("reports") or []) for er in (r.get("errors") or [])]
    if errors:
        lines.append("")
        lines.append("## Ошибки")
        for kind, er in errors:
            reason = er.get("reason") if isinstance(er, dict) else str(er)
            ident = er.get("id") if isinstance(er, dict) else ""
            lines.append(f"- **{kind}/{ident}**: {reason}")
    return "\n".join(lines)


# --- Откат последнего импорта (ТЗ §4.1) -------------------------------------
# kind → имя модуля сервиса с EntityStore (store() + get/delete).
_ENTITY_STORE_KINDS = {
    "item": "item_constructor_service",
    "effect": "effect_constructor_service",
    "skill": "skill_constructor_service",
    "fine_def": "fine_constructor_service",
    "recipe": "recipe_constructor_service",
    "achievement": "achievement_service",
    "profile_layout": "profile_layout_service",
    "city_node": "city_constructor_service",
    "trait": "trait_constructor_service",
    "blessing": "blessing_constructor_service",
    "phase": "phase_constructor_service",
    "race": "race_constructor_service",
    "reputation": "reputation_constructor_service",
    "city_shop_item": "city_constructor_service",
    "text": "text_constructor_service",
}
# kind → имя константы вида реестра мира (world_content_registry без отдельного store()).
_WCR_KINDS = {"mob": "KIND_MOB", "location": "KIND_LOCATION", "event": "KIND_EVENT"}


def _journal_path():
    import os
    from project_paths import project_path

    override = os.environ.get("IMPORT_JOURNAL_PATH")
    if override:
        from pathlib import Path

        return Path(override)
    return project_path("data", "import_journal.json")


def save_import_journal(batch) -> None:
    import json

    path = _journal_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    payload = {"created": [[str(k), str(s)] for k, s in batch], "count": len(list(batch))}
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def load_import_journal():
    import json

    path = _journal_path()
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def _delete_imported(kind: str, sid: str) -> str:
    """Удалить одну запись отката. Статус: deleted/kept/missing/unknown.

    kept — запись больше не помечена imported (админ взял её под контроль, §11):
    откат её НЕ трогает."""
    if kind in _WCR_KINDS:
        from services import world_content_registry as wcr

        kconst = getattr(wcr, _WCR_KINDS[kind])
        env = wcr.get_content(kconst, sid)
        if env is None:
            return "missing"
        if not (env.get("data") or {}).get("imported"):
            return "kept"
        wcr.delete_content(kconst, sid)
        return "deleted"
    module_name = _ENTITY_STORE_KINDS.get(kind)
    if not module_name:
        return "unknown"
    import importlib

    module = importlib.import_module(f"services.{module_name}")
    store = module.store()
    env = store.get(sid)
    if env is None:
        return "missing"
    if not (env.get("data") or {}).get("imported"):
        return "kept"
    store.delete(sid)
    return "deleted"


def rollback_last(*, actor: str = "import") -> dict[str, Any]:
    """Откатить последний реальный импорт: удалить созданные им записи (§4.1).

    Удаляются только записи, всё ещё помеченные imported (рукотворные/взятые
    админом под контроль — сохраняются). Журнал после отката очищается."""
    journal = load_import_journal()
    created = (journal or {}).get("created") or []
    counts = {"deleted": 0, "kept": 0, "missing": 0, "unknown": 0}
    details: list[dict[str, Any]] = []
    for entry in created:
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            continue
        kind, sid = str(entry[0]), str(entry[1])
        status = _delete_imported(kind, sid)
        counts[status] = counts.get(status, 0) + 1
        if status in ("kept", "unknown"):
            details.append({"kind": kind, "id": sid, "status": status})
    save_import_journal([])  # журнал израсходован — повторный откат ничего не делает
    _BATCH.clear()
    return {"ok": True, "found": len(created), **counts, "details": details}
