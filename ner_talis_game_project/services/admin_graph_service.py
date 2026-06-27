"""Единый граф связей админ-панели (ТЗ 12, бэкенд-фундамент).

Собирает все игровые сущности из разных конструкторов/реестров в один граф
nodes/edges и отдаёт его в разных режимах: вся карта, по типу, вокруг объекта,
только ошибки, карта локации, путь между объектами. Это чистый агрегатор —
ничего не мутирует, лишь читает существующие сторы и валидаторы.

Узел: {id:"<type>:<entity_id>", type, title, status, has_errors, errors[],
       warnings[], external?}.
Ребро: {id, from, to, type, label, broken?}.

Связи строятся по декларативной таблице REF_SPECS (только подтверждённые поля
конструкторов — чтобы не плодить ложные рёбра). Битым считается ребро, чья
цель не найдена ни среди узлов, ни в каталоге предметов.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Callable, Iterable

from services import world_content_registry as wcr

# --- Человекочитаемые подписи ---------------------------------------------
NODE_TYPE_LABELS: dict[str, str] = {
    "location": "Локация", "mob": "Моб", "button": "Кнопка", "transition": "Переход",
    "event": "Событие", "npc": "NPC", "quest": "Задание", "raid": "Рейд",
    "location_zone": "Зона локации", "location_resource": "Ресурс",
    "location_loot": "Добыча", "location_mob_spawn": "Спавн моба",
    "location_weekly_limit": "Недельный лимит", "location_weekly_rotation": "Ротация",
    "location_depletion_rule": "Истощение", "location_empty_event": "Пустая локация",
    "location_hidden_event": "Скрытое событие", "location_event_answer": "Вариант ответа",
    "mob_variant": "Вариант моба", "mob_skill": "Навык моба", "mob_passive": "Пассивка моба",
    "mob_resistance": "Сопротивление", "mob_effect": "Эффект моба",
    "mob_event_link": "Моб↔событие", "mob_zone_link": "Моб↔зона", "mob_phase": "Фаза моба",
    "item": "Предмет", "recipe": "Рецепт", "effect": "Эффект", "trait": "Черта",
    "blessing": "Благословение", "phase": "Фаза боя", "level": "Уровень",
    "skill": "Навык", "race": "Раса", "fine": "Штраф", "camp": "Лагерь",
    "city": "Город", "achievement": "Достижение",
    "world_event": "Мировое событие", "guild": "Гильдия",
    "sublocation": "Подлокация", "sublocation_node": "Узел подлокации",
    "sublocation_transition": "Переход подлокации", "formula": "Формула",
    "profession": "Профессия", "workshop": "Мастерская",
    "workshop_message": "Сообщение мастерской",
    "item_upgrade": "Улучшение", "item_enchant": "Зачарование",
    "item_disassemble": "Разборка",
    # Сайт (ТЗ §16) и профиль — из своих реестров с тегом _kind.
    "site_page": "Страница сайта", "site_page_block": "Блок страницы",
    "site_menu_item": "Пункт меню", "site_news": "Новость", "site_guide": "Гайд",
    "site_faq": "FAQ", "site_banner": "Баннер", "site_announcement": "Объявление",
    "site_post": "Пост", "site_rating": "Рейтинг", "site_lore": "Лор",
    "site_where_is": "Что где", "site_theme": "Тема сайта",
    "profile_tab": "Вкладка профиля", "profile_block": "Блок профиля",
    "profile_theme": "Тема профиля",
}

EDGE_TYPE_LABELS: dict[str, str] = {
    "contains": "содержит", "leads_to": "ведёт к", "in_location": "в локации",
    "from_location": "из локации", "to_location": "в локацию",
    "spawns": "появляется", "drops": "выпадает", "gives_item": "выдаёт предмет",
    "requires_item": "требует предмет", "consumes_item": "списывает предмет",
    "sells_item": "продаёт", "buys_item": "покупает", "applies_effect": "накладывает эффект",
    "starts_battle": "запускает бой", "triggers_event": "запускает событие",
    "given_by": "выдаёт", "uses_item": "использует предмет",
    "produces": "создаёт", "ingredient": "ингредиент", "blueprint": "по чертежу",
    "rewards_item": "награждает предметом", "in_category": "в категории",
    "in_zone": "в зоне", "in_page": "в странице", "child_of": "вложен в",
    "in_tab": "во вкладке", "uses_formula": "использует формулу",
    "uses_profession": "требует профессию", "in_workshop": "в мастерской",
    "disassembles": "разбирает", "enchants": "зачаровывает",
}

# Поля-ссылки на формулу по типу узла (ТЗ 13 §2.8). Любой конструктор, в data
# которого есть эти ключи, автоматически связывается с узлом формулы.
FORMULA_REF_FIELDS: dict[str, tuple[str, ...]] = {
    "level": ("formula_id", "exp_formula_id"),
    "exp": ("formula_id",),
    "recipe": ("result_formula_id", "time_formula_id", "cost_formula_id", "exp_formula_id"),
    "event": ("chance_formula_id",),
    "location": ("search_depth_formula_id",),
    "mob": ("exp_formula_id", "damage_formula_id"),
    "fine": ("amount_formula_id",),
    "profession": ("exp_formula_id", "next_level_formula_id"),
}

# --- Декларативные спецификации связей -------------------------------------
# (extractor, path, target_type, edge_type)
#   extractor: "scalar" | "list" | "listdict"
#   path: ключ data (для listdict — "outer.inner" + subkey задаётся в 5-м поле)
# Целевой тип может быть кортежем кандидатов (резолвится по первому существующему).
SCALAR, LIST, LISTDICT = "scalar", "list", "listdict"

REF_SPECS: dict[str, list[tuple]] = {
    wcr.KIND_BUTTON: [
        (SCALAR, "owner_location", "location", "in_location"),
        (SCALAR, "target", "location", "leads_to", "goto_location"),  # только при action=goto_location
    ],
    wcr.KIND_TRANSITION: [
        (SCALAR, "from_location", "location", "from_location"),
        (SCALAR, "to_location", "location", "to_location"),
    ],
    wcr.KIND_EVENT: [
        (SCALAR, "location", "location", "in_location"),
        (SCALAR, "battle_mob", "mob", "starts_battle"),
        (SCALAR, "given_item", "item", "gives_item"),
        (SCALAR, "required_item", "item", "requires_item"),
        (SCALAR, "consumed_item", "item", "consumes_item"),
    ],
    wcr.KIND_NPC: [
        (SCALAR, "location", "location", "in_location"),
        (LIST, "event_ids", ("event", "location_hidden_event"), "triggers_event"),
        (LISTDICT, "trade.sells", "item", "sells_item", "item_id"),
        (LISTDICT, "trade.buys", "item", "buys_item", "item_id"),
    ],
    wcr.KIND_QUEST: [
        (SCALAR, "npc_giver", "npc", "given_by"),
        (SCALAR, "location", "location", "in_location"),
    ],
    wcr.KIND_RAID: [
        (SCALAR, "entry_location", "location", "in_location"),
        (SCALAR, "boss_mob", "mob", "starts_battle"),
    ],
    wcr.KIND_LOCATION_ZONE: [
        (SCALAR, "location", "location", "in_location"),
    ],
    wcr.KIND_LOCATION_RESOURCE: [
        (SCALAR, "location", "location", "in_location"),
        (SCALAR, "item_id", "item", "gives_item"),
    ],
    wcr.KIND_LOCATION_LOOT: [
        (SCALAR, "location", "location", "in_location"),
        (SCALAR, "item_id", "item", "gives_item"),
    ],
    wcr.KIND_LOCATION_MOB_SPAWN: [
        (SCALAR, "location", "location", "in_location"),
        (SCALAR, "mob_id", "mob", "spawns"),
    ],
    wcr.KIND_LOCATION_WEEKLY_LIMIT: [
        (SCALAR, "location", "location", "in_location"),
    ],
    wcr.KIND_LOCATION_WEEKLY_ROTATION: [
        (SCALAR, "location", "location", "in_location"),
    ],
    wcr.KIND_LOCATION_DEPLETION_RULE: [
        (SCALAR, "location", "location", "in_location"),
    ],
    wcr.KIND_LOCATION_EMPTY_EVENT: [
        (SCALAR, "location", "location", "in_location"),
    ],
    wcr.KIND_LOCATION_HIDDEN_EVENT: [
        (SCALAR, "location", "location", "in_location"),
        (SCALAR, "given_item", "item", "gives_item"),
        (SCALAR, "battle_mob", "mob", "starts_battle"),
    ],
    wcr.KIND_LOCATION_EVENT_ANSWER: [
        (SCALAR, "required_item", "item", "requires_item"),
        (SCALAR, "reward_item", "item", "rewards_item"),
    ],
    wcr.KIND_MOB_VARIANT: [(SCALAR, "mob_id", "mob", "in_location")],
    wcr.KIND_MOB_SKILL: [(SCALAR, "mob_id", "mob", "in_location")],
    wcr.KIND_MOB_PASSIVE: [(SCALAR, "mob_id", "mob", "in_location")],
    wcr.KIND_MOB_RESISTANCE: [(SCALAR, "mob_id", "mob", "in_location")],
    wcr.KIND_MOB_EFFECT: [
        (SCALAR, "mob_id", "mob", "in_location"),
        (SCALAR, "effect_id", "effect", "applies_effect"),
    ],
    wcr.KIND_MOB_EVENT_LINK: [
        (SCALAR, "mob_id", "mob", "in_location"),
        (SCALAR, "event_id", ("event", "location_hidden_event"), "triggers_event"),
    ],
    wcr.KIND_MOB_ZONE_LINK: [
        (SCALAR, "mob_id", "mob", "in_location"),
        (SCALAR, "zone_id", "location_zone", "in_zone"),
    ],
    wcr.KIND_MOB_PHASE: [(SCALAR, "mob_id", "mob", "in_location")],
    wcr.KIND_SUBLOCATION: [
        (SCALAR, "parent_location", "location", "in_location"),
    ],
    wcr.KIND_SUBLOCATION_NODE: [
        (SCALAR, "sublocation_id", "sublocation", "in_location"),
    ],
    wcr.KIND_SUBLOCATION_TRANSITION: [
        (SCALAR, "sublocation_id", "sublocation", "in_location"),
        (SCALAR, "from_node", "sublocation_node", "from_location"),
        (SCALAR, "to_node", "sublocation_node", "to_location"),
        (SCALAR, "required_item", "item", "requires_item"),
    ],
}

# Конструкторы на EntityStore: (node_type, модуль-сервис, поле-заголовок).
# Импортируются лениво — каждый стор автономен и может отсутствовать в тестах.
CONSTRUCTOR_SOURCES: list[tuple[str, str, str]] = [
    ("item", "item_constructor_service", "name"),
    ("recipe", "recipe_constructor_service", "name"),
    ("effect", "effect_constructor_service", "effect_name"),
    ("trait", "trait_constructor_service", "trait_name"),
    ("blessing", "blessing_constructor_service", "blessing_name"),
    ("phase", "phase_constructor_service", "name"),
    ("level", "level_constructor_service", "title"),
    ("skill", "skill_constructor_service", "skill_name"),
    ("race", "race_constructor_service", "race_name"),
    ("fine", "fine_constructor_service", "name"),
    ("camp", "camp_constructor_service", "name"),
    ("city", "city_constructor_service", "city_name"),
    ("achievement", "achievement_service", "name"),
    ("world_event", "world_event_service", "name"),
    ("guild", "guild_service", "name"),
    ("formula", "formula_constructor_service", "name"),
    ("profession", "profession_constructor_service", "name"),
    ("workshop", "workshop_constructor_service", "name"),
    ("workshop_message", "workshop_message_service", "name"),
    ("item_upgrade", "upgrade_constructor_service", "name"),
    ("item_enchant", "enchant_constructor_service", "name"),
    ("item_disassemble", "disassemble_constructor_service", "name"),
]

# Реестры с тегом _kind в data (сайт/профиль): один стор — много типов узлов.
# (node_type_prefix, модуль, использовать_kind_как_есть)
KINDED_SOURCES: list[tuple[str, str, bool]] = [
    ("site_", "site_content_registry", False),  # _kind="page" → site_page
    ("", "profile_layout_service", True),       # _kind="profile_tab" уже с префиксом
]


def node_id(node_type: str, entity_id: str) -> str:
    return f"{node_type}:{entity_id}"


def _import_service(module_name: str):
    try:
        import importlib

        return importlib.import_module(f"services.{module_name}")
    except Exception:
        return None


def _entity_title(data: dict[str, Any], title_field: str, fallback: str) -> str:
    for key in (title_field, "name", "title", "admin_name"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return fallback


# --- Сбор узлов ------------------------------------------------------------
def _world_nodes() -> dict[str, dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}
    for kind in wcr.KINDS:
        try:
            envelopes = wcr.list_content(kind)
        except Exception:
            continue
        for env in envelopes:
            eid = str(env.get("id") or "")
            if not eid:
                continue
            nid = node_id(kind, eid)
            check = wcr.validate_envelope(env)
            data = env.get("data") or {}
            nodes[nid] = {
                "id": nid, "type": kind, "entity_id": eid,
                "title": _entity_title(data, "name", eid),
                "status": env.get("status"),
                "has_errors": not check.get("ok", True),
                "errors": check.get("errors", []),
                "warnings": check.get("warnings", []),
                "updated_at": env.get("updated_at"),
                "updated_by": env.get("updated_by"),
            }
    return nodes


def _constructor_nodes() -> dict[str, dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}
    for node_type, module_name, title_field in CONSTRUCTOR_SOURCES:
        svc = _import_service(module_name)
        if svc is None or not hasattr(svc, "store"):
            continue
        try:
            envelopes = svc.store().list()
        except Exception:
            continue
        validate: Callable | None = getattr(svc, "validate", None)
        for env in envelopes:
            eid = str(env.get("id") or "")
            if not eid:
                continue
            nid = node_id(node_type, eid)
            data = env.get("data") or {}
            errors: list[str] = []
            warnings: list[str] = []
            if callable(validate):
                try:
                    check = validate(env)
                    errors = list(check.get("errors", []))
                    warnings = list(check.get("warnings", []))
                except Exception:
                    pass
            nodes[nid] = {
                "id": nid, "type": node_type, "entity_id": eid,
                "title": _entity_title(data, title_field, eid),
                "status": env.get("status"),
                "has_errors": bool(errors),
                "errors": errors, "warnings": warnings,
                "updated_at": env.get("updated_at"),
                "updated_by": env.get("updated_by"),
            }
    return nodes


def _kinded_nodes() -> dict[str, dict[str, Any]]:
    """Узлы из реестров с тегом _kind (сайт §16, профиль): один стор — много типов."""
    nodes: dict[str, dict[str, Any]] = {}
    for prefix, module_name, kind_is_full in KINDED_SOURCES:
        svc = _import_service(module_name)
        if svc is None or not hasattr(svc, "store"):
            continue
        try:
            envelopes = svc.store().list()
        except Exception:
            continue
        for env in envelopes:
            eid = str(env.get("id") or "")
            data = env.get("data") or {}
            kind = str(data.get("_kind") or "")
            if not eid or not kind:
                continue
            node_type = kind if kind_is_full else f"{prefix}{kind}"
            nid = node_id(node_type, eid)
            title = (data.get("title") or data.get("label") or data.get("question")
                     or data.get("name") or eid)
            nodes[nid] = {
                "id": nid, "type": node_type, "entity_id": eid,
                "title": str(title), "status": env.get("status"),
                "has_errors": False, "errors": [], "warnings": [],
                "updated_at": env.get("updated_at"),
                "updated_by": env.get("updated_by"),
            }
    return nodes


# Рёбра реестров с _kind: (node_type, поле, целевой_тип, тип_ребра).
KINDED_EDGE_SPECS: list[tuple[str, str, str, str]] = [
    ("site_page_block", "page_id", "site_page", "in_page"),
    ("site_menu_item", "page_id", "site_page", "leads_to"),
    ("site_menu_item", "parent_id", "site_menu_item", "child_of"),
    ("profile_block", "tab", "profile_tab", "in_tab"),
]


def _item_exists_in_registry(item_id: str) -> bool:
    try:
        from services.item_registry import get_item_definition_by_id

        return get_item_definition_by_id(item_id) is not None
    except Exception:
        return False


# --- Извлечение ссылок -----------------------------------------------------
def _as_id_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
    return []


def _extract_refs(spec: tuple, data: dict[str, Any]) -> list[str]:
    extractor, path = spec[0], spec[1]
    if extractor == SCALAR:
        # Условный extractor: 5-е поле = требуемое значение data["action"].
        if len(spec) >= 5:
            if str(data.get("action") or "") != spec[4]:
                return []
        val = data.get(path)
        return [str(val).strip()] if str(val or "").strip() else []
    if extractor == LIST:
        return _as_id_list(data.get(path))
    if extractor == LISTDICT:
        subkey = spec[4] if len(spec) >= 5 else "item_id"
        outer, _, inner = path.partition(".")
        container = data.get(outer)
        if inner:
            container = (container or {}).get(inner) if isinstance(container, dict) else None
        out: list[str] = []
        if isinstance(container, list):
            for row in container:
                if isinstance(row, dict) and str(row.get(subkey) or "").strip():
                    out.append(str(row[subkey]).strip())
        return out
    return []


def _resolve_target(ref_id: str, target_type, nodes: dict[str, dict[str, Any]]):
    """Вернуть (node_id, resolved) — resolved=False если цель не найдена."""
    candidates = target_type if isinstance(target_type, tuple) else (target_type,)
    for t in candidates:
        nid = node_id(t, ref_id)
        if nid in nodes:
            return nid, True
    # Предмет может жить только в runtime-каталоге — это не битая ссылка.
    if "item" in candidates and _item_exists_in_registry(ref_id):
        nid = node_id("item", ref_id)
        if nid not in nodes:
            nodes[nid] = {
                "id": nid, "type": "item", "entity_id": ref_id,
                "title": ref_id, "status": "external", "external": True,
                "has_errors": False, "errors": [], "warnings": [],
            }
        return nid, True
    # Цель не найдена — создаём узел-плейсхолдер «не найден» (ТЗ §9), чтобы
    # битая связь была видна на схеме, а не отбрасывалась подграфом.
    nid = node_id(candidates[0], ref_id)
    if nid not in nodes:
        nodes[nid] = {
            "id": nid, "type": candidates[0], "entity_id": ref_id,
            "title": f"{ref_id} (не найден)", "status": "missing", "missing": True,
            "has_errors": True, "errors": [f"Объект «{ref_id}» не существует."],
            "warnings": [],
        }
    return nid, False


def _collect_edges(nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    seen: set[str] = set()
    for nid, node in list(nodes.items()):
        specs = REF_SPECS.get(node["type"])
        if not specs:
            continue
        env_data = _node_data(node)
        if env_data is None:
            continue
        for spec in specs:
            target_type, edge_type = spec[2], spec[3]
            for ref_id in _extract_refs(spec, env_data):
                target_id, resolved = _resolve_target(ref_id, target_type, nodes)
                eid = f"{nid}|{edge_type}|{target_id}"
                if eid in seen:
                    continue
                seen.add(eid)
                edge = {
                    "id": eid, "from": nid, "to": target_id,
                    "type": edge_type, "label": EDGE_TYPE_LABELS.get(edge_type, edge_type),
                }
                if not resolved:
                    edge["broken"] = True
                    node["has_errors"] = True
                    node.setdefault("errors", []).append(
                        f"Связь «{edge['label']}» ведёт в несуществующий объект: {ref_id}."
                    )
                edges.append(edge)
    # Рёбра конструкторов (recipe→item, achievement→item) — отдельной логикой.
    edges.extend(_constructor_edges(nodes, seen))
    # Рёбра сайта/профиля (реестры с _kind).
    edges.extend(_kinded_edges(nodes, seen))
    # Рёбра «использует формулу» (ТЗ 13 §2.8).
    edges.extend(_formula_edges(nodes, seen))
    return edges


def _formula_edges(nodes: dict[str, dict[str, Any]], seen: set[str]) -> list[dict[str, Any]]:
    """Связи объектов с формулами по полям *_formula_id (ТЗ 13 §2.8)."""
    edges: list[dict[str, Any]] = []
    for nid, node in list(nodes.items()):
        fields = FORMULA_REF_FIELDS.get(node["type"])
        if not fields:
            continue
        data = _node_data(node)
        if data is None:
            continue
        for field in fields:
            ref = str(data.get(field) or "").strip()
            if not ref:
                continue
            target_id, resolved = _resolve_target(ref, "formula", nodes)
            eid = f"{nid}|uses_formula|{target_id}"
            if eid in seen:
                continue
            seen.add(eid)
            edge = {"id": eid, "from": nid, "to": target_id, "type": "uses_formula",
                    "label": EDGE_TYPE_LABELS["uses_formula"]}
            if not resolved:
                edge["broken"] = True
                nodes[nid]["has_errors"] = True
                nodes[nid].setdefault("errors", []).append(
                    f"Ссылка на несуществующую формулу: {ref}.")
            edges.append(edge)
    return edges


def _node_data(node: dict[str, Any]) -> dict[str, Any] | None:
    """Перечитать data объекта по его типу/id (world или конструктор)."""
    ntype, eid = node["type"], node.get("entity_id")
    if not eid:
        return None
    if ntype in wcr.KINDS:
        env = wcr.get_content(ntype, eid)
        return (env or {}).get("data") if env else None
    for node_type, module_name, _ in CONSTRUCTOR_SOURCES:
        if node_type == ntype:
            svc = _import_service(module_name)
            if svc and hasattr(svc, "store"):
                try:
                    env = svc.store().get(eid)
                    return (env or {}).get("data") if env else None
                except Exception:
                    return None
    return None


def _constructor_edges(nodes: dict[str, dict[str, Any]], seen: set[str]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []

    def _add(from_nid: str, ref_id: str, edge_type: str) -> None:
        target_id, resolved = _resolve_target(ref_id, "item", nodes)
        eid = f"{from_nid}|{edge_type}|{target_id}"
        if eid in seen:
            return
        seen.add(eid)
        edge = {"id": eid, "from": from_nid, "to": target_id,
                "type": edge_type, "label": EDGE_TYPE_LABELS.get(edge_type, edge_type)}
        if not resolved:
            edge["broken"] = True
            if from_nid in nodes:
                nodes[from_nid]["has_errors"] = True
                nodes[from_nid].setdefault("errors", []).append(
                    f"Связь «{edge['label']}» ведёт в несуществующий предмет: {ref_id}.")
        edges.append(edge)

    def _add_typed(from_nid: str, ref_id: str, target_type: str, edge_type: str) -> None:
        target_id, resolved = _resolve_target(ref_id, target_type, nodes)
        eid = f"{from_nid}|{edge_type}|{target_id}"
        if eid in seen:
            return
        seen.add(eid)
        edge = {"id": eid, "from": from_nid, "to": target_id, "type": edge_type,
                "label": EDGE_TYPE_LABELS.get(edge_type, edge_type)}
        if not resolved:
            edge["broken"] = True
            if from_nid in nodes:
                nodes[from_nid]["has_errors"] = True
        edges.append(edge)

    for nid, node in list(nodes.items()):
        if node["type"] == "recipe":
            data = _node_data(node) or {}
            if str(data.get("output_item_id") or "").strip():
                _add(nid, str(data["output_item_id"]).strip(), "produces")
            for row in (data.get("ingredients") or []):
                if isinstance(row, dict) and str(row.get("item_id") or "").strip():
                    _add(nid, str(row["item_id"]).strip(), "ingredient")
            if str(data.get("blueprint_id") or "").strip():
                _add(nid, str(data["blueprint_id"]).strip(), "blueprint")
            if str(data.get("profession") or "").strip():
                _add_typed(nid, str(data["profession"]).strip(), "profession", "uses_profession")
            if str(data.get("workshop_id") or "").strip():
                _add_typed(nid, str(data["workshop_id"]).strip(), "workshop", "in_workshop")
        elif node["type"] == "workshop_message":
            data = _node_data(node) or {}
            if str(data.get("workshop_id") or "").strip():
                _add_typed(nid, str(data["workshop_id"]).strip(), "workshop", "in_workshop")
        elif node["type"] == "achievement":
            data = _node_data(node) or {}
            for row in (data.get("rewards") or []):
                if isinstance(row, dict) and str(row.get("type") or "") in ("item", "unique_item"):
                    if str(row.get("item_id") or "").strip():
                        _add(nid, str(row["item_id"]).strip(), "rewards_item")
                if isinstance(row, dict) and str(row.get("type") or "") == "effect" and str(row.get("effect_id") or "").strip():
                    _add_typed(nid, str(row["effect_id"]).strip(), "effect", "applies_effect")
            # Эффекты достижения (ТЗ 09 §17): список effects (id или {effect_id}).
            for entry in (data.get("effects") or []):
                ref = entry.get("effect_id") if isinstance(entry, dict) else entry
                if str(ref or "").strip():
                    _add_typed(nid, str(ref).strip(), "effect", "applies_effect")
        elif node["type"] == "workshop":
            data = _node_data(node) or {}
            loc = str(data.get("location") or "").strip()
            if loc:
                target_id, resolved = _resolve_target(loc, "location", nodes)
                eid = f"{nid}|in_location|{target_id}"
                if eid not in seen:
                    seen.add(eid)
                    edge = {"id": eid, "from": nid, "to": target_id, "type": "in_location",
                            "label": EDGE_TYPE_LABELS["in_location"]}
                    if not resolved:
                        edge["broken"] = True
                        nodes[nid]["has_errors"] = True
                    edges.append(edge)
        elif node["type"] == "item_disassemble":
            data = _node_data(node) or {}
            if str(data.get("source_item_id") or "").strip():
                _add(nid, str(data["source_item_id"]).strip(), "disassembles")
            for row in (data.get("outputs") or []):
                ref = row.get("item_id") if isinstance(row, dict) else row
                if str(ref or "").strip():
                    _add(nid, str(ref).strip(), "produces")
        elif node["type"] == "item_enchant":
            data = _node_data(node) or {}
            if str(data.get("enchant_effect") or "").strip():
                _add_typed(nid, str(data["enchant_effect"]).strip(), "effect", "applies_effect")
        elif node["type"] == "item_upgrade":
            data = _node_data(node) or {}
            if str(data.get("result_effect") or "").strip():
                _add_typed(nid, str(data["result_effect"]).strip(), "effect", "applies_effect")
    return edges


def _kinded_edges(nodes: dict[str, dict[str, Any]], seen: set[str]) -> list[dict[str, Any]]:
    """Рёбра сайта/профиля (page_block→page, menu_item→page, block→tab)."""
    edges: list[dict[str, Any]] = []
    for prefix, module_name, kind_is_full in KINDED_SOURCES:
        svc = _import_service(module_name)
        if svc is None or not hasattr(svc, "store"):
            continue
        try:
            envelopes = svc.store().list()
        except Exception:
            continue
        for env in envelopes:
            data = env.get("data") or {}
            kind = str(data.get("_kind") or "")
            eid = str(env.get("id") or "")
            if not kind or not eid:
                continue
            node_type = kind if kind_is_full else f"{prefix}{kind}"
            from_nid = node_id(node_type, eid)
            if from_nid not in nodes:
                continue
            for spec_type, field, target_type, edge_type in KINDED_EDGE_SPECS:
                if spec_type != node_type:
                    continue
                ref_id = str(data.get(field) or "").strip()
                if not ref_id:
                    continue
                target_id, resolved = _resolve_target(ref_id, target_type, nodes)
                eidk = f"{from_nid}|{edge_type}|{target_id}"
                if eidk in seen:
                    continue
                seen.add(eidk)
                edge = {"id": eidk, "from": from_nid, "to": target_id,
                        "type": edge_type,
                        "label": EDGE_TYPE_LABELS.get(edge_type, edge_type)}
                if not resolved:
                    edge["broken"] = True
                    nodes[from_nid]["has_errors"] = True
                    nodes[from_nid].setdefault("errors", []).append(
                        f"Связь «{edge['label']}» ведёт в несуществующий объект: {ref_id}.")
                edges.append(edge)
    return edges


# --- Построение полного графа и режимы -------------------------------------
def _build_all() -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    nodes = _world_nodes()
    nodes.update(_constructor_nodes())
    nodes.update(_kinded_nodes())
    edges = _collect_edges(nodes)
    return nodes, edges


def _subgraph(nodes: dict[str, dict[str, Any]], edges: list[dict[str, Any]],
              keep: set[str]) -> dict[str, Any]:
    kept_nodes = [n for nid, n in nodes.items() if nid in keep]
    kept_edges = [e for e in edges if e["from"] in keep and e["to"] in keep]
    return {"nodes": kept_nodes, "edges": kept_edges}


def _adjacency(edges: list[dict[str, Any]]) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = {}
    for e in edges:
        adj.setdefault(e["from"], set()).add(e["to"])
        adj.setdefault(e["to"], set()).add(e["from"])
    return adj


def full_graph(*, types: Iterable[str] | None = None,
               statuses: Iterable[str] | None = None) -> dict[str, Any]:
    nodes, edges = _build_all()
    type_set = set(types) if types else None
    status_set = set(statuses) if statuses else None
    keep = {
        nid for nid, n in nodes.items()
        if (type_set is None or n["type"] in type_set)
        and (status_set is None or n.get("status") in status_set)
    }
    return _subgraph(nodes, edges, keep)


def graph_around(target: str, *, depth: int = 2) -> dict[str, Any]:
    nodes, edges = _build_all()
    if target not in nodes:
        return {"nodes": [], "edges": [], "error": f"Объект {target} не найден."}
    adj = _adjacency(edges)
    keep: set[str] = {target}
    frontier = {target}
    for _ in range(max(0, int(depth))):
        nxt: set[str] = set()
        for n in frontier:
            for m in adj.get(n, ()):
                if m not in keep:
                    nxt.add(m)
        keep |= nxt
        frontier = nxt
        if not frontier:
            break
    return _subgraph(nodes, edges, keep)


def error_graph() -> dict[str, Any]:
    nodes, edges = _build_all()
    bad_nodes = {nid for nid, n in nodes.items() if n.get("has_errors")}
    # Узлы на концах битых рёбер тоже включаем для контекста.
    for e in edges:
        if e.get("broken"):
            bad_nodes.add(e["from"])
            bad_nodes.add(e["to"])
    # Сироты (без единой связи) — отдельная категория ошибок структуры.
    connected = {e["from"] for e in edges} | {e["to"] for e in edges}
    orphans = {nid for nid in nodes if nid not in connected}
    keep = bad_nodes | orphans
    out = _subgraph(nodes, edges, keep)
    out["orphans"] = sorted(orphans)
    return out


def location_graph(location_id: str) -> dict[str, Any]:
    loc_nid = node_id("location", location_id)
    return graph_around(loc_nid, depth=1)


def path_graph(source: str, target: str) -> dict[str, Any]:
    nodes, edges = _build_all()
    if source not in nodes or target not in nodes:
        return {"nodes": [], "edges": [], "path": [], "found": False,
                "error": "Один из объектов не найден."}
    adj = _adjacency(edges)
    prev: dict[str, str] = {source: source}
    q: deque[str] = deque([source])
    while q:
        cur = q.popleft()
        if cur == target:
            break
        for nxt in adj.get(cur, ()):
            if nxt not in prev:
                prev[nxt] = cur
                q.append(nxt)
    if target not in prev:
        return {"nodes": [], "edges": [], "path": [], "found": False,
                "error": "Путь между объектами не найден."}
    path: list[str] = []
    cur = target
    while True:
        path.append(cur)
        if cur == source:
            break
        cur = prev[cur]
    path.reverse()
    keep = set(path)
    out = _subgraph(nodes, edges, keep)
    out["path"] = path
    out["found"] = True
    return out


def node_detail(target: str) -> dict[str, Any] | None:
    nodes, edges = _build_all()
    node = nodes.get(target)
    if node is None:
        return None
    outgoing = [e for e in edges if e["from"] == target]
    incoming = [e for e in edges if e["to"] == target]
    return {
        "node": node,
        "outgoing": outgoing,
        "incoming": incoming,
        "used_by": sorted({e["from"] for e in incoming}),
    }


def validate_graph() -> dict[str, Any]:
    nodes, edges = _build_all()
    broken = [e for e in edges if e.get("broken")]
    error_nodes = [n for n in nodes.values() if n.get("has_errors")]
    connected = {e["from"] for e in edges} | {e["to"] for e in edges}
    orphans = [nid for nid in nodes if nid not in connected]
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "broken_edges": broken,
        "error_node_count": len(error_nodes),
        "orphan_count": len(orphans),
        "orphans": orphans,
    }


def legend() -> dict[str, Any]:
    return {
        "nodeTypes": [{"value": k, "label": v} for k, v in NODE_TYPE_LABELS.items()],
        "edgeTypes": [{"value": k, "label": v} for k, v in EDGE_TYPE_LABELS.items()],
    }


def build(mode: str = "full", **params: Any) -> dict[str, Any]:
    """Диспетчер режимов для роутера."""
    mode = str(mode or "full")
    if mode == "around":
        return graph_around(str(params.get("focus") or ""),
                            depth=int(params.get("depth") or 2))
    if mode == "errors":
        return error_graph()
    if mode == "location":
        return location_graph(str(params.get("location_id") or ""))
    if mode == "path":
        return path_graph(str(params.get("source") or ""), str(params.get("target") or ""))
    types = params.get("types")
    statuses = params.get("statuses")
    return full_graph(types=types, statuses=statuses)


# --- Экспорт схемы (ТЗ §20, §22) -------------------------------------------
def export_markdown(graph: dict[str, Any]) -> str:
    """Markdown-отчёт по графу: узлы по типам, связи, ошибки."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    by_type: dict[str, list[dict[str, Any]]] = {}
    for n in nodes:
        by_type.setdefault(n.get("type", "?"), []).append(n)
    lines = ["# Схема Нер-Талис", "",
             f"Узлов: **{len(nodes)}**, связей: **{len(edges)}**.", ""]
    broken = [e for e in edges if e.get("broken")]
    error_nodes = [n for n in nodes if n.get("has_errors")]
    if error_nodes or broken:
        lines += ["## Проблемы", "",
                  f"- Узлов с ошибками: **{len(error_nodes)}**",
                  f"- Битых связей: **{len(broken)}**", ""]
    lines.append("## Узлы по типам")
    lines.append("")
    for ntype in sorted(by_type):
        label = NODE_TYPE_LABELS.get(ntype, ntype)
        lines.append(f"### {label} ({len(by_type[ntype])})")
        for n in sorted(by_type[ntype], key=lambda x: str(x.get("title") or x.get("id"))):
            mark = " ⚠️" if n.get("has_errors") else ""
            status = n.get("status") or "—"
            lines.append(f"- {n.get('title') or n.get('id')} — `{n.get('id')}` [{status}]{mark}")
        lines.append("")
    lines.append("## Связи")
    lines.append("")
    for e in edges:
        mark = " ⚠️ (битая)" if e.get("broken") else ""
        lines.append(f"- `{e.get('from')}` —{e.get('label')}→ `{e.get('to')}`{mark}")
    return "\n".join(lines)


def export(mode: str = "full", fmt: str = "json", **params: Any) -> dict[str, Any]:
    """Экспорт схемы выбранного режима в JSON или Markdown."""
    graph = build(mode, **params)
    fmt = str(fmt or "json").lower()
    if fmt in ("md", "markdown"):
        return {"format": "md", "filename": f"graph_{mode}.md",
                "content": export_markdown(graph)}
    return {"format": "json", "filename": f"graph_{mode}.json", "content": graph}


# --- Редактирование связей на схеме (ТЗ 12 §34) ----------------------------
# Только безопасные FK-связи: одно скалярное поле на объекте-источнике.
# (from_type, edge_type) → {field, target}.
EDITABLE_EDGES: dict[tuple[str, str], dict[str, str]] = {
    ("recipe", "uses_profession"): {"field": "profession", "target": "profession"},
    ("recipe", "in_workshop"): {"field": "workshop_id", "target": "workshop"},
    ("workshop", "in_location"): {"field": "location", "target": "location"},
    ("workshop_message", "in_workshop"): {"field": "workshop_id", "target": "workshop"},
    ("sublocation", "in_location"): {"field": "parent_location", "target": "location"},
}


def editable_edge_specs() -> list[dict[str, Any]]:
    """Описание редактируемых связей для UI (тип источника/ребра/цели + подписи)."""
    out: list[dict[str, Any]] = []
    for (from_type, edge_type), spec in EDITABLE_EDGES.items():
        out.append({
            "from_type": from_type, "from_label": NODE_TYPE_LABELS.get(from_type, from_type),
            "edge_type": edge_type, "edge_label": EDGE_TYPE_LABELS.get(edge_type, edge_type),
            "target_type": spec["target"],
            "target_label": NODE_TYPE_LABELS.get(spec["target"], spec["target"]),
        })
    return out


def _write_node_field(node_type: str, entity_id: str, field: str, value: str, actor: str) -> None:
    if node_type in wcr.KINDS:
        env = wcr.get_content(node_type, entity_id)
        if env is None:
            raise ValueError(f"Объект {node_type}:{entity_id} не найден.")
        data = dict(env.get("data") or {})
        data[field] = value
        wcr.update_content(node_type, entity_id, data, actor=actor)
        return
    for nt, module_name, _ in CONSTRUCTOR_SOURCES:
        if nt == node_type:
            svc = _import_service(module_name)
            if svc is None or not hasattr(svc, "store"):
                raise ValueError("Хранилище недоступно.")
            env = svc.store().get(entity_id)
            if env is None:
                raise ValueError(f"Объект {node_type}:{entity_id} не найден.")
            data = dict(env.get("data") or {})
            data[field] = value
            svc.store().update(entity_id, data, actor=actor)
            return
    raise ValueError(f"Тип {node_type} не поддерживает редактирование связей.")


def _split_node_id(node_id: str) -> tuple[str, str]:
    ntype, _, eid = str(node_id or "").partition(":")
    return ntype, eid


def set_edge(from_id: str, edge_type: str, to_id: str, *, actor: str = "") -> dict[str, Any]:
    """Создать/изменить связь: записать целевой id в FK-поле источника (§34)."""
    from_type, from_eid = _split_node_id(from_id)
    spec = EDITABLE_EDGES.get((from_type, edge_type))
    if not spec:
        raise ValueError("Эта связь не редактируется на схеме.")
    to_type, to_eid = _split_node_id(to_id)
    if to_type and to_type != spec["target"]:
        raise ValueError(f"Цель должна быть типа «{NODE_TYPE_LABELS.get(spec['target'], spec['target'])}».")
    _write_node_field(from_type, from_eid, spec["field"], to_eid, actor)
    return {"from": from_id, "edge_type": edge_type, "to": f"{spec['target']}:{to_eid}"}


def clear_edge(from_id: str, edge_type: str, *, actor: str = "") -> dict[str, Any]:
    """Удалить связь: очистить FK-поле источника (§34, опасное действие)."""
    from_type, from_eid = _split_node_id(from_id)
    spec = EDITABLE_EDGES.get((from_type, edge_type))
    if not spec:
        raise ValueError("Эта связь не редактируется на схеме.")
    _write_node_field(from_type, from_eid, spec["field"], "", actor)
    return {"from": from_id, "edge_type": edge_type, "cleared": True}


# --- Тестовая песочница из схемы (ТЗ 12 §19) -------------------------------
def sandbox_run(node_id: str, *, values: dict[str, Any] | None = None,
                target: str | None = None) -> dict[str, Any]:
    """Сухой прогон объекта без изменения реального игрока: валидация, тип-
    специфичная проверка, битые связи, какие сообщения/награды были бы выданы,
    и (если задан target) проходимость пути."""
    nodes, edges = _build_all()
    node = nodes.get(node_id)
    if node is None:
        return {"ok": False, "error": f"Объект {node_id} не найден.", "steps": []}
    ntype, eid = _split_node_id(node_id)
    data = _node_data(node) or {}
    steps: list[dict[str, Any]] = []

    def _step(title: str, status: str, detail: str = "") -> None:
        steps.append({"title": title, "status": status, "detail": detail})

    _step("Проверка объекта", "error" if node.get("has_errors") else "ok",
          "; ".join(node.get("errors") or []) or "без ошибок")
    for w in (node.get("warnings") or []):
        _step("Предупреждение", "warn", w)

    # Тип-специфичный сухой прогон.
    if ntype == "formula":
        svc = _import_service("formula_constructor_service")
        if svc:
            res = svc.test_formula(data, values or {})
            if res.get("ok"):
                _step("Расчёт формулы", "ok", f"Результат: {res.get('result')}")
            else:
                _step("Расчёт формулы", "error", "; ".join(res.get("errors") or []))
    elif ntype in wcr.KINDS:
        try:
            tr = wcr.test_run(ntype, eid)
            if tr:
                for c in tr.get("checks", []):
                    _step(f"Связанный: {c.get('title')}", "ok" if c.get("ok") else "error",
                          "; ".join(c.get("errors") or []))
        except Exception:
            pass
    if ntype == "sublocation":
        try:
            sch = wcr.validate_sublocation_schema(eid)
            _step("Схема подлокации", "ok" if sch.get("ok") else "error",
                  "; ".join(sch.get("errors") or []) or f"узлов {sch.get('node_count')}")
        except Exception:
            pass

    # Битые исходящие связи блокируют путь.
    broken = [e for e in edges if e["from"] == node_id and e.get("broken")]
    for e in broken:
        _step("Битая связь", "error", f"{e['label']} → {e['to']}")

    # Что было бы выдано/отправлено (без выполнения).
    if any(data.get(k) for k in ("player_message", "scene_message", "notify_message")):
        _step("Сообщение игроку", "info", "Будет показано сообщение игроку.")
    rewards = data.get("rewards")
    if isinstance(rewards, list) and rewards:
        _step("Награды", "info", f"Будут выданы награды: {len(rewards)}.")
    if str(data.get("given_item") or data.get("output_item_id") or "").strip():
        _step("Выдача предмета", "info",
              f"Будет выдан предмет: {data.get('given_item') or data.get('output_item_id')}.")

    out: dict[str, Any] = {"node": node, "steps": steps}
    # Режим пути (§10/§19): проходимость от node к target.
    if target:
        pg = path_graph(node_id, target)
        if pg.get("found"):
            path = pg.get("path", [])
            blocked = [e for e in pg.get("edges", []) if e.get("broken")]
            out["path"] = path
            if blocked:
                _step("Путь", "error", "Путь содержит битые связи — заблокирован.")
            else:
                _step("Путь", "ok", " → ".join(path))
        else:
            _step("Путь", "error", pg.get("error") or "Путь не найден.")

    out["ok"] = not any(s["status"] == "error" for s in steps)
    return out
