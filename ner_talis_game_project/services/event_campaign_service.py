"""Конструктор полноценных игровых эвентов (ТЗ 2.0, файл 08, часть 4)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403

EVENT_TYPES = ("seasonal", "holiday", "combat", "pve", "pvp", "craft", "fishing", "resource", "economy", "story", "quest", "world", "personal", "group", "server", "test")
TASK_TYPES = ("kill_mob", "kill_boss", "gather_resource", "catch_fish", "craft_item", "complete_recipe", "visit_location", "talk_npc", "finish_event", "complete_quest", "buy_item", "sell_item", "spend_currency", "gain_currency", "send_item", "use_promo", "telegram_reaction", "vk_like", "special")
REWARD_TYPES = ("item", "currency", "experience", "energy", "effect", "achievement", "title", "skill", "recipe", "access", "reputation", "hidden_reputation")
RATING_TYPES = ("points", "tasks", "contribution", "speed", "pve", "pvp", "craft", "resource")

_store = EntityStore(env_var="EVENT_CAMPAIGNS_PATH", default_rel="data/event_campaigns.json",
                     statuses=STATUSES, transitions=TRANSITIONS, initial_status=STATUS_DRAFT)  # noqa: F405

def store() -> EntityStore: return _store
def _num(v: Any) -> float | None:
    try: return float(v)
    except (TypeError, ValueError): return None
def _dt(v: Any) -> datetime | None:
    try: return datetime.fromisoformat(str(v).replace("Z", "+00:00")) if v else None
    except ValueError: return None

def validate(env: dict[str, Any]) -> dict[str, Any]:
    d=env.get("data") or {}; errors=[]; warnings=[]
    if not str(d.get("name") or d.get("player_name") or "").strip(): errors.append("Не заполнено название эвента.")
    if str(d.get("event_type") or "") not in EVENT_TYPES: errors.append("Не выбран допустимый тип эвента.")
    start,end=_dt(d.get("start_at")),_dt(d.get("end_at"))
    if d.get("start_at") and not start: errors.append("Некорректная дата начала.")
    if d.get("end_at") and not end: errors.append("Некорректная дата окончания.")
    if start and end and start>=end: errors.append("Дата окончания должна быть позже начала.")
    if not d.get("endless") and not end: warnings.append("Не задано окончание эвента.")
    stages=d.get("stages") or []; stage_ids=set()
    for i,row in enumerate(stages,1):
        if not isinstance(row,dict): errors.append(f"Этап #{i}: неверный формат."); continue
        sid=str(row.get("stage_id") or "").strip()
        if not sid: errors.append(f"Этап #{i}: нет ID.")
        elif sid in stage_ids: errors.append(f"Этап #{i}: повтор ID {sid}.")
        stage_ids.add(sid)
    task_ids=set()
    for i,row in enumerate(d.get("tasks") or [],1):
        if not isinstance(row,dict): errors.append(f"Задача #{i}: неверный формат."); continue
        tid=str(row.get("task_id") or "").strip(); typ=str(row.get("task_type") or "")
        if not tid: errors.append(f"Задача #{i}: нет ID.")
        elif tid in task_ids: errors.append(f"Задача #{i}: повтор ID {tid}.")
        task_ids.add(tid)
        if typ not in TASK_TYPES: errors.append(f"Задача #{i}: неизвестный тип {typ}.")
        if (_num(row.get("required_count")) or 0)<=0: errors.append(f"Задача #{i}: количество должно быть больше нуля.")
        if row.get("stage_id") and str(row.get("stage_id")) not in stage_ids: errors.append(f"Задача #{i}: этап не найден.")
    for i,row in enumerate(d.get("rewards") or [],1):
        if not isinstance(row,dict) or str(row.get("type") or "") not in REWARD_TYPES: errors.append(f"Награда #{i}: неверный тип.")
    if d.get("rating_enabled") and str(d.get("rating_type") or "") not in RATING_TYPES: errors.append("Не выбран тип рейтинга.")
    if d.get("registration_required") and d.get("all_players"): warnings.append("Одновременно включены все игроки и обязательная регистрация.")
    if d.get("registration_required") and not any((d.get("registration_via_button",True),d.get("registration_via_npc"),d.get("registration_via_item"))):errors.append("Для обязательной регистрации не выбран ни один способ.")
    if d.get("registration_via_item") and not str(d.get("registration_item_id") or "").strip():errors.append("Для регистрации через предмет не выбран предмет.")
    if d.get("registration_item_id"):
        try:
            from services.item_registry import get_item_definition_by_id
            if not get_item_definition_by_id(str(d.get("registration_item_id"))):errors.append("Предмет регистрации не существует.")
        except Exception:warnings.append("Не удалось проверить предмет регистрации.")
    for i,row in enumerate(stages,1):
        if not isinstance(row,dict):continue
        stage_start,stage_end=_dt(row.get("start_at")),_dt(row.get("end_at"))
        if row.get("start_at") and not stage_start:errors.append(f"Этап #{i}: некорректная дата начала.")
        if row.get("end_at") and not stage_end:errors.append(f"Этап #{i}: некорректная дата окончания.")
        if stage_start and stage_end and stage_start>=stage_end:errors.append(f"Этап #{i}: окончание должно быть позже начала.")
    for i,row in enumerate(d.get("rewards") or [],1):
        if not isinstance(row,dict):continue
        if str(row.get("scope") or "final") not in {"participation","task","stage","rating","final"}:errors.append(f"Награда #{i}: неизвестная область получения.")
        if str(row.get("scope") or "") == "rating" and not any(row.get(key) for key in ("place","place_from","min_place","place_to","max_place")):warnings.append(f"Награда #{i}: рейтинговая награда без места применяется всем участникам рейтинга.")
    try:
        from services import broadcast_constructor_service as broadcasts,world_event_service as world_events
        for raw in d.get("broadcast_ids") or []:
            row=raw if isinstance(raw,dict) else {"broadcast_id":raw};ref=str(row.get("broadcast_id") or row.get("id") or "")
            env=broadcasts.store().get(ref) if ref else None
            if not env or env.get("status")!=broadcasts.STATUS_PUBLISHED:errors.append(f"Рассылка эвента «{ref or '—'}» не найдена или не опубликована.")
        for ref in d.get("world_event_ids") or []:
            env=world_events.store().get(str(ref))
            if not env:errors.append(f"Мировое событие эвента «{ref}» не найдено.")
    except Exception:warnings.append("Не удалось проверить рассылки и мировые события эвента.")
    return {"ok":not errors,"errors":errors,"warnings":warnings}

def published(event_id: str) -> dict[str, Any] | None:
    env=_store.get(str(event_id)); return dict(env.get("data") or {}) if env and env.get("status")==STATUS_PUBLISHED else None  # noqa: F405

def preview(data: dict[str, Any]) -> dict[str, Any]:
    return {"name":data.get("player_name") or data.get("name"),"type":data.get("event_type"),
            "period":{"start":data.get("start_at"),"end":data.get("end_at"),"endless":bool(data.get("endless"))},
            "stages":len(data.get("stages") or []),"tasks":len(data.get("tasks") or []),
            "rewards":len(data.get("rewards") or []),"rating":bool(data.get("rating_enabled"))}
