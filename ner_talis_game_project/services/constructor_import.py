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


def import_items(*, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    from services.item_registry import load_all_item_definitions
    from services import item_constructor_service as ics

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


def import_mobs(*, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    from services.pve_battle_service import BATTLE_MOB_CATALOGS
    from services import world_content_registry as wcr

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


def import_effects(*, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    from services import effect_constructor_service as ecs

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


def import_skills(*, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    from services import active_skill_service as ass
    from services import skill_constructor_service as scs

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


# --- Оркестратор -----------------------------------------------------------
IMPORTERS = {"item": import_items, "mob": import_mobs, "effect": import_effects, "skill": import_skills}


def import_all(kinds: list[str] | None = None, *, overwrite: bool = False, actor: str = "import") -> dict[str, Any]:
    selected = [k for k in (kinds or list(IMPORTERS)) if k in IMPORTERS]
    reports = [IMPORTERS[k](overwrite=overwrite, actor=actor) for k in selected]
    return {"ok": True, "reports": reports}
