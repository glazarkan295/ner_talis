"""Конструктор квестов и заданий (ТЗ 2.0, файл 10, часть 2).

Запись = квест/задание: этапы, задачи, диалоги, ветвления, награды, провал,
повторяемость. Опубликованные записи исполняет quest_runtime_service.

Модель хранения — плоские коллекции внутри записи (LibrarySection-friendly):
``stages`` (этапы), ``tasks`` (задачи; привязка к этапу через ``stage_id``),
``choices`` (ветвления), ``rewards`` (награды), ``quest_items`` (предметы),
``dialogs`` (реплики NPC). Ссылки между этапами проверяются на существование и
на отсутствие бесконечного цикла.

Хранение — EntityStore (data/quest_constructor.json).
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")

# Типы квестов (§26).
QUEST_TYPES = (
    "story", "side", "daily", "weekly", "repeatable", "one_time", "hidden",
    "secret", "npc", "board", "combat", "pve", "pvp", "craft", "fishing",
    "resource", "delivery", "criminal", "penalty", "reputation", "event",
    "world", "tutorial", "service",
)
QUEST_TYPE_LABELS = {
    "story": "Сюжетный", "side": "Побочный", "daily": "Ежедневный",
    "weekly": "Еженедельный", "repeatable": "Повторяемый", "one_time": "Одноразовый",
    "hidden": "Скрытый", "secret": "Секретный", "npc": "NPC-квест",
    "board": "Доска заданий", "combat": "Боевой", "pve": "PVE", "pvp": "PVP",
    "craft": "Ремесленный", "fishing": "Рыболовный", "resource": "Ресурсный",
    "delivery": "Доставочный", "criminal": "Криминальный", "penalty": "Штрафной",
    "reputation": "Репутационный", "event": "Эвентовый", "world": "Мировой",
    "tutorial": "Обучающий", "service": "Служебный",
}
# Источники выдачи (§27).
SOURCE_TYPES = (
    "npc", "board", "item", "event", "location", "sublocation", "camp",
    "city", "fortress", "achievement", "world_event", "promo", "admin", "auto",
)
# Типы задач (§30).
TASK_TYPES = (
    "talk_npc", "visit_location", "visit_sublocation", "open_camp", "find_item",
    "bring_item", "use_item", "equip_item", "craft_item", "disassemble_item",
    "upgrade_item", "enchant_item", "catch_fish", "gather_resource", "kill_mob",
    "kill_mob_group", "kill_boss", "kill_player", "survive_turns", "pass_event",
    "dialog_choice", "pay_penalty", "deliver_item", "buy_item", "sell_item",
    "gain_reputation", "change_hidden_reputation", "event_action",
    "activate_promo", "special",
)
# Типы наград (§35).
REWARD_TYPES = (
    "item", "currency", "exp", "energy", "skill_points", "stat_points", "skill",
    "effect", "achievement", "title", "reputation", "hidden_reputation",
    "access_location", "access_sublocation", "access_camp", "access_npc",
    "access_market", "recipe", "promo", "system_flag",
)
# Повторяемость (§37).
REPEAT_MODES = (
    "one_time", "repeatable", "daily", "weekly", "monthly", "seasonal", "event",
)
CURRENCIES = ("copper", "silver", "gold", "magic_gold", "ancient_coin")
ACCEPT_CONDITION_TYPES=("item","achievement","previous_quest","completed_quest","failed_quest","reputation","hidden_reputation","location","sublocation","npc","effect","no_fine","has_fine","event_campaign","world_event","time","weekday")

_store = EntityStore(
    env_var="QUEST_CONSTRUCTOR_PATH",
    default_rel="data/quest_constructor.json",
    statuses=STATUSES,  # noqa: F405
    transitions=TRANSITIONS,  # noqa: F405
    initial_status=STATUS_DRAFT,  # noqa: F405
)


def store() -> EntityStore:
    return _store


def published_definition(quest_id: str) -> dict[str, Any] | None:
    env = store().get(str(quest_id or ""))
    if not env or env.get("status") != STATUS_PUBLISHED:  # noqa: F405
        return None
    return {"id": env.get("id"), **dict(env.get("data") or {})}


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_html(value: Any) -> bool:
    s = str(value or "")
    return bool(_HTML_RE.search(s)) or "<script" in s.lower()


def _stage_ids(data: dict[str, Any]) -> set[str]:
    return {
        str(s.get("stage_id") or "").strip()
        for s in (data.get("stages") or [])
        if isinstance(s, dict) and str(s.get("stage_id") or "").strip()
    }


def has_stage_cycle(stages: list[dict[str, Any]]) -> bool:
    """True, если переходы этапов (next_stage) образуют бесконечный цикл (§41)."""
    graph: dict[str, list[str]] = {}
    for s in stages or []:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("stage_id") or "").strip()
        if not sid:
            continue
        nxt = []
        for key in ("next_stage", "alt_stage"):
            v = str(s.get(key) or "").strip()
            if v:
                nxt.append(v)
        graph.setdefault(sid, []).extend(nxt)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {sid: WHITE for sid in graph}

    def visit(node: str) -> bool:
        color[node] = GRAY
        for nb in graph.get(node, []):
            if nb not in color:  # ссылка наружу графа — не цикл
                continue
            if color[nb] == GRAY:
                return True
            if color[nb] == WHITE and visit(nb):
                return True
        color[node] = BLACK
        return False

    return any(color.get(sid) == WHITE and visit(sid) for sid in list(graph))


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not str(data.get("name") or "").strip():
        errors.append("Не заполнено название квеста.")

    qtype = str(data.get("quest_type") or "").strip()
    if not qtype:
        errors.append("Не выбран тип квеста.")
    elif qtype not in QUEST_TYPES:
        errors.append(f"Неизвестный тип квеста: {qtype}.")

    src = str(data.get("source_type") or "").strip()
    if src and src not in SOURCE_TYPES:
        warnings.append(f"Источник выдачи «{src}» не из списка.")

    # Уровни (§25/§28).
    for key, label in (("level", "Уровень квеста"), ("min_level", "Минимальный уровень"),
                       ("max_level", "Максимальный уровень"),
                       ("recommended_level", "Рекомендуемый уровень")):
        if data.get(key) not in (None, "") and (_num(data.get(key)) is None or _num(data.get(key)) < 0):
            errors.append(f"{label}: неотрицательное число.")
    lo, hi = _num(data.get("min_level")), _num(data.get("max_level"))
    if lo is not None and hi is not None and lo > hi:
        errors.append("Минимальный уровень больше максимального.")

    # Условия завершения (§34) — обязательны.
    completion = data.get("completion_conditions") or []
    if not [c for c in completion if str(c or "").strip()]:
        errors.append("Не заданы условия завершения квеста.")

    # Этапы (§29): уникальные ID, валидные переходы, без бесконечного цикла.
    stages = data.get("stages") or []
    stage_ids = _stage_ids(data)
    seen: set[str] = set()
    for i, s in enumerate(stages, start=1):
        if not isinstance(s, dict):
            continue
        sid = str(s.get("stage_id") or "").strip()
        if not sid:
            warnings.append(f"Этап #{i}: не задан ID этапа.")
            continue
        if sid in seen:
            errors.append(f"Этап #{i}: дублируется ID «{sid}».")
        seen.add(sid)
        for key, kl in (("next_stage", "следующий этап"), ("alt_stage", "альтернативный этап"),
                        ("fail_stage", "этап провала")):
            ref = str(s.get(key) or "").strip()
            if ref and ref not in stage_ids:
                errors.append(f"Этап #{i}: {kl} «{ref}» не существует.")
    if has_stage_cycle([s for s in stages if isinstance(s, dict)]):
        errors.append("Этапы образуют бесконечный цикл (§41).")

    # Задачи (§30): тип из списка, привязка к этапу, количество ≥ 0.
    for i, t in enumerate(data.get("tasks") or [], start=1):
        if not isinstance(t, dict):
            continue
        ttype = str(t.get("task_type") or "").strip()
        if ttype and ttype not in TASK_TYPES:
            warnings.append(f"Задача #{i}: тип «{ttype}» не из списка.")
        if t.get("required_count") not in (None, "") and (_num(t.get("required_count")) is None or _num(t.get("required_count")) < 0):
            errors.append(f"Задача #{i}: требуемое количество — неотрицательное число.")
        st = str(t.get("stage_id") or "").strip()
        if st and stage_ids and st not in stage_ids:
            errors.append(f"Задача #{i}: этап «{st}» не существует.")
    for i,row in enumerate(data.get("accept_conditions") or [],start=1):
        if isinstance(row,dict) and str(row.get("type") or "") not in ACCEPT_CONDITION_TYPES:errors.append(f"Условие принятия #{i}: неизвестный тип.")
    for i,row in enumerate(data.get("quest_items") or [],start=1):
        if not isinstance(row,dict) or not str(row.get("item_id") or ""):errors.append(f"Квестовый предмет #{i}: не указан ID.")
        elif (_num(row.get("count")) or 0)<=0:errors.append(f"Квестовый предмет #{i}: количество должно быть больше нуля.")
    choice_ids=set()
    for i,row in enumerate(data.get("choices") or [],start=1):
        if not isinstance(row,dict):continue
        cid=str(row.get("choice_id") or "")
        if not cid:errors.append(f"Выбор #{i}: не указан ID.")
        elif cid in choice_ids:errors.append(f"Выбор #{i}: дублируется ID «{cid}».")
        choice_ids.add(cid)
        if row.get("next_stage") and str(row["next_stage"]) not in stage_ids:errors.append(f"Выбор #{i}: следующий этап не существует.")

    # Награды (§35): тип из списка.
    for i, r in enumerate(data.get("rewards") or [], start=1):
        if isinstance(r, dict):
            rt = str(r.get("type") or "").strip()
            if rt and rt not in REWARD_TYPES:
                warnings.append(f"Награда #{i}: тип «{rt}» не из списка.")

    # Повторяемость (§37).
    repeat = str(data.get("repeat_mode") or "").strip()
    if repeat and repeat not in REPEAT_MODES:
        warnings.append(f"Режим повторяемости «{repeat}» не из списка.")
    if repeat in ("repeatable", "daily", "weekly", "monthly", "seasonal") and (_num(data.get("repeat_cooldown_seconds")) or 0) <= 0:
        warnings.append("Квест повторяемый, но не задан кулдаун повтора (§41).")

    # Сроки (§37).
    if data.get("deadline_seconds") not in (None, ""):
        if _num(data.get("deadline_seconds")) is None or _num(data.get("deadline_seconds")) < 0:
            errors.append("Срок выполнения — неотрицательное число.")
        elif not str(data.get("timer_text") or "").strip():
            warnings.append("У квеста есть срок, но нет текста таймера (§41).")

    # Предупреждения §41.
    if not (data.get("rewards") or []):
        warnings.append("У квеста нет наград.")
    if not str(data.get("source_npc_id") or "").strip() and src == "npc":
        warnings.append("Источник — NPC, но NPC не указан.")
    if (qtype in ("hidden", "secret") or data.get("hidden")) and not data.get("reveal_condition"):
        warnings.append("Квест скрытый, но нет условия открытия.")

    # Тексты без HTML.
    for key in ("name", "description", "hidden_description", "appear_text", "accept_text", "decline_text", "complete_text", "reward_text", "fail_text", "stage_text", "task_text", "progress_text", "task_complete_text", "unavailable_text", "missing_item_text", "wrong_npc_text", "wrong_location_text", "repeat_text", "reveal_text"):
        if _has_html(data.get(key)):
            errors.append(f"В поле «{key}» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}

def import_legacy(*,actor:str="")->dict[str,Any]:
    """Import legacy world quests preserving IDs; player quest state is untouched."""
    from services import world_content_registry as world
    created=skipped=0;ids=[]
    for env in world.list_content(world.KIND_QUEST):
        qid=str(env.get("id") or "")
        if not qid or store().get(qid):skipped+=1;continue
        old=dict(env.get("data") or {});data={"name":old.get("name") or old.get("title") or qid,"quest_type":old.get("quest_type") or "side","description":old.get("description") or old.get("text") or "","source_type":old.get("source_type") or ("npc" if old.get("npc_id") else "auto"),"source_npc_id":old.get("npc_id") or old.get("source_npc_id"),"completion_conditions":old.get("completion_conditions") or ["all_tasks_done"],"stages":old.get("stages") or [{"stage_id":"main","name":"Основной этап"}],"tasks":old.get("tasks") or [],"rewards":old.get("rewards") or [],"repeat_mode":old.get("repeat_mode") or "one_time","legacy_imported":True}
        store().create(qid,data,actor=actor);store().set_status(qid,STATUS_PUBLISHED,actor=actor,force=True);created+=1;ids.append(qid)
    return {"created":created,"skipped":skipped,"ids":ids}


def preview(data: dict[str, Any]) -> dict[str, Any]:
    """Предпросмотр квеста (§38)."""
    data = data or {}
    stages = [
        {"stage_id": s.get("stage_id"), "name": s.get("name"), "text": s.get("player_text")}
        for s in (data.get("stages") or []) if isinstance(s, dict)
    ]
    tasks = [
        {"type": QUEST_TYPE_LABELS.get(str(t.get("task_type") or ""), str(t.get("task_type") or "")),
         "target": t.get("target_name") or t.get("target_id"), "count": t.get("required_count")}
        for t in (data.get("tasks") or []) if isinstance(t, dict)
    ]
    rewards = [
        {"type": r.get("type"), "id": r.get("object_id"), "count": r.get("count")}
        for r in (data.get("rewards") or []) if isinstance(r, dict)
    ]
    return {
        "name": data.get("name") or "Квест",
        "quest_type": QUEST_TYPE_LABELS.get(str(data.get("quest_type") or ""), str(data.get("quest_type") or "—")),
        "appear_text": data.get("appear_text") or data.get("description") or "",
        "stages": stages,
        "tasks": tasks,
        "rewards": rewards,
        "repeatable": str(data.get("repeat_mode") or "") not in ("", "one_time"),
    }
