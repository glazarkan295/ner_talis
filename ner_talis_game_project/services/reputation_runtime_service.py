"""Runtime опубликованной открытой/скрытой репутации (ТЗ 2.0 §51–64)."""
from __future__ import annotations

from datetime import datetime, timezone
import threading,time
from typing import Any

from services import reputation_constructor_service as definitions

HISTORY_LIMIT = 500
_worker_started=False;_worker_lock=threading.Lock()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def published_definition(reputation_id: str) -> dict[str, Any] | None:
    env = definitions.store().get(str(reputation_id or ""))
    if not env or env.get("status") != definitions.STATUS_PUBLISHED:
        return None
    return dict(env.get("data") or {})


def published_definitions() -> list[tuple[str, dict[str, Any]]]:
    return [(str(env.get("id")), dict(env.get("data") or {}))
            for env in definitions.store().list(status=definitions.STATUS_PUBLISHED)]


def value(player: dict[str, Any], reputation_id: str) -> float:
    data = published_definition(reputation_id) or {}
    key="hidden_reputations" if str(data.get("visibility") or data.get("reputation_type") or "") == "hidden" else "reputations"
    values = player.get(key) if isinstance(player.get(key), dict) else {}
    # Read legacy saves without exposing them through player_view.
    if key=="hidden_reputations" and str(reputation_id) not in values and isinstance(player.get("reputations"),dict):values=player["reputations"]
    return _num(values.get(str(reputation_id)), _num(data.get("default_value")))

def _stage_outcomes(player,reputation_id,data,stage):
    if not isinstance(stage,dict):return
    stage_id=str(stage.get("stage_id") or "");claim=f"{reputation_id}:{stage_id}";claims=player.setdefault("reputation_stage_claims",[])
    if not stage_id or claim in claims:return
    for row in stage.get("rewards") or []:
        if not isinstance(row,dict):continue
        kind=str(row.get("type") or "");oid=str(row.get("object_id") or row.get("item_id") or "");amount=max(1,int(_num(row.get("amount"),1)))
        if kind=="achievement" and oid:player.setdefault("achievement_progress",{})[oid]={"completed":True,"source":"reputation"}
        elif kind=="reputation":continue
        else:
            from services.quest_runtime_service import _grant
            _grant(player,{"type":{"experience":"exp","access":"system_flag"}.get(kind,kind),"object_id":oid,"amount":amount},quest_id=f"reputation:{reputation_id}")
    for row in stage.get("accesses") or []:
        if not isinstance(row,dict):continue
        oid=str(row.get("object_id") or row.get("id") or "");typ=str(row.get("type") or "")
        if oid:player.setdefault("unlocks",{})[f"{typ}:{oid}"]=True;player["unlocks"][oid]=True
    restrictions=[dict(row) for row in stage.get("restrictions") or [] if isinstance(row,dict)]
    if restrictions:player.setdefault("reputation_restrictions",{})[str(reputation_id)]=restrictions
    claims.append(claim);player["reputation_stage_claims"]=claims[-500:]


def change(player: dict[str, Any], reputation_id: str, delta: Any, *, source: str,
           source_id: str = "", reason: str = "", admin: str = "", rule_id: str = "") -> dict[str, Any]:
    data = published_definition(reputation_id)
    if data is None:
        raise ValueError("Репутация не опубликована.")
    current = value(player, reputation_id)
    effective_delta=_num(delta)
    if data.get("use_change_formula") and data.get("change_formula_id"):
        from services.formula_runtime import evaluate
        effective_delta=_num(evaluate(str(data["change_formula_id"]),{"base_amount":effective_delta,"current_reputation":current,"source_id":source_id},default=effective_delta),effective_delta)
    next_value = current + effective_delta
    if data.get("min_value") not in (None, ""):
        next_value = max(_num(data.get("min_value")), next_value)
    if data.get("max_value") not in (None, ""):
        next_value = min(_num(data.get("max_value")), next_value)
    if data.get("allow_negative") is False:next_value=max(0,next_value)
    hidden=str(data.get("visibility") or data.get("reputation_type") or "") == "hidden";values = player.setdefault("hidden_reputations" if hidden else "reputations", {})
    values[str(reputation_id)] = next_value
    if hidden and isinstance(player.get("reputations"),dict):player["reputations"].pop(str(reputation_id),None)
    row = {
        "reputation_id": str(reputation_id), "old_value": current,
        "new_value": next_value, "change": next_value - current,
        "source": str(source), "source_id": str(source_id or ""),
        "at": datetime.now(timezone.utc).isoformat(), "reason": str(reason or ""),
    }
    if rule_id:row["rule_id"]=str(rule_id)
    if admin:
        row["admin"] = str(admin)
    history = player.setdefault("reputation_history", [])
    history.append(row)
    if len(history) > HISTORY_LIMIT:
        del history[:-HISTORY_LIMIT]
    preview = definitions.preview(data, current, next_value - current)
    if preview.get("stage_changed"):_stage_outcomes(player,str(reputation_id),data,preview.get("next_stage"))
    if data.get("show_change_notifications") is not False:
        hidden=str(data.get("visibility") or data.get("reputation_type") or "") == "hidden"
        if not hidden or data.get("show_hints"):
            name=str(data.get("player_name") or data.get("name_ru") or data.get("name") or reputation_id);text=(str(reason) if reason else f"Репутация «{name}» изменилась.") if not hidden else str(data.get("hint_text") or "Вы чувствуете, что чьё-то отношение к вам изменилось.")
            player.setdefault("pending_bot_messages",[]).append({"type":"reputation","text":text,"source":f"reputation:{reputation_id}"})
    try:
        from services.achievement_engine import record_game_event
        record_game_event(player,"hidden_reputation" if str(data.get("visibility") or "") == "hidden" else "reputation",next_value,str(reputation_id))
    except Exception:pass
    return {**row, "stage": preview.get("next_stage"), "stage_changed": preview.get("stage_changed"),
            "marks": preview.get("next_marks") or []}


def apply_trigger(player: dict[str, Any], trigger: str, source_id: str = "", *,
                  reason: str = "") -> list[dict[str, Any]]:
    """Применить все опубликованные правила, совпавшие с игровым событием."""
    results: list[dict[str, Any]] = []
    canonical={"quest_complete":"quest","quest_fail":"quest","event_choice":"event","pvp_kill":"pvp","fine_unpaid":"fine","trade":"purchase","raid":"pve"}.get(str(trigger),str(trigger));accepted={str(trigger),canonical}
    for reputation_id, data in published_definitions():
        for rule in data.get("change_rules") or []:
            if not isinstance(rule, dict) or str(rule.get("trigger") or "") not in accepted:
                continue
            expected = str(rule.get("source_id") or rule.get("trigger_id") or rule.get("object_id") or "")
            if expected and expected != str(source_id or ""):
                continue
            rule_id=str(rule.get("rule_id") or f"{trigger}:{expected}");limit=max(0,int(_num(rule.get("daily_limit"))))
            if limit:
                today=datetime.now(timezone.utc).date();used=sum(1 for row in player.get("reputation_history") or [] if isinstance(row,dict) and row.get("reputation_id")==reputation_id and row.get("rule_id")==rule_id and str(row.get("at") or "")[:10]==today.isoformat())
                if used>=limit:continue
            amount = _num(rule.get("change_value"))
            if rule.get("formula_id"):
                from services.formula_runtime import evaluate
                amount=_num(evaluate(str(rule["formula_id"]),{"base_amount":amount,"current_reputation":value(player,reputation_id),"source_id":source_id},default=amount),amount)
            mode = str(rule.get("change_mode") or rule.get("value_type") or "fixed")
            if mode in ("percent", "percentage"):
                amount = (_num(data.get("max_value")) - _num(data.get("min_value"))) * amount / 100.0
            if str(rule.get("direction") or "") in ("negative","minus") and amount>0:amount=-amount
            results.append(change(player, reputation_id, amount, source=trigger,
                                  source_id=source_id, reason=reason or str(rule.get("text") or ""),rule_id=rule_id))
    return results


def player_view(player: dict[str, Any]) -> list[dict[str, Any]]:
    """Только разрешённые игроку репутации; скрытые значения не протекают."""
    rows: list[dict[str, Any]] = []
    for reputation_id, data in published_definitions():
        if str(data.get("visibility") or "visible") == "hidden" or data.get("show_to_player") is False:
            continue
        current = value(player, reputation_id)
        stage = definitions.stage_for_value(data, current) or {}
        row = {"id": reputation_id, "name": data.get("name_ru") or data.get("name"),
               "stage": stage.get("name_ru") or stage.get("name") or stage.get("stage_id")}
        if data.get("show_exact_value") is not False and str(data.get("display_mode") or "number") != "stage":
            row["value"] = current
        rows.append(row)
    return rows


def economic_modifiers(player: dict[str, Any]) -> dict[str, float | bool]:
    out: dict[str, float | bool] = {"buy_discount_percent": 0.0, "sell_bonus_percent": 0.0,
                                    "fine_modifier_percent": 0.0, "market_commission_percent": 0.0,
                                    "delivery_commission_percent": 0.0, "bad_reputation_markup_percent":0.0,
                                    "service_price_percent":0.0,"hidden_products":False,"trade_blocked": False}
    for reputation_id, data in published_definitions():
        stage = definitions.stage_for_value(data, value(player, reputation_id)) or {}
        merged = {**data, **stage}
        for key in tuple(out):
            if key in ("trade_blocked","hidden_products"):
                out[key] = bool(out[key]) or bool(merged.get(key) or merged.get("trade_forbidden"))
            else:
                out[key] = float(out[key]) + _num(merged.get(key))
    return out

def price_by_reputation(player:dict[str,Any],base:int,context:dict[str,Any]|None=None)->int:
    amount=max(0,int(base))
    for reputation_id,data in published_definitions():
        stage=definitions.stage_for_value(data,value(player,reputation_id)) or {};formula_id=str(stage.get("price_formula_id") or data.get("price_formula_id") or "")
        if not formula_id:continue
        from services.formula_runtime import evaluate
        amount=max(0,int(_num(evaluate(formula_id,{"base_amount":amount,"price":amount,"reputation_value":value(player,reputation_id),**(context or {})},default=amount),amount)))
    return amount

def apply_decay(player:dict[str,Any],*,now:datetime|None=None)->list[dict[str,Any]]:
    moment=now or datetime.now(timezone.utc);state=player.setdefault("reputation_decay_state",{});results=[]
    for reputation_id,data in published_definitions():
        if not data.get("decay_enabled"):continue
        interval=max(1,int(_num(data.get("decay_interval_seconds"),1)));last_raw=state.get(reputation_id)
        try:last=datetime.fromisoformat(str(last_raw).replace("Z","+00:00")) if last_raw else moment
        except ValueError:last=moment
        periods=max(0,int((moment-last).total_seconds()//interval));state[reputation_id]=last.isoformat() if not periods else moment.isoformat()
        if not periods:continue
        current=value(player,reputation_id);amount=abs(_num(data.get("decay_amount")))*periods;direction=str(data.get("decay_direction") or "toward_default");target=_num(data.get("default_value")) if direction=="toward_default" else 0
        if direction in ("toward_zero","toward_default"):delta=min(amount,abs(target-current))*(1 if current<target else -1)
        elif direction=="down_only":delta=-amount
        else:delta=amount
        if delta:results.append(change(player,reputation_id,delta,source="decay",reason="Естественное изменение репутации"))
    return results

def start_worker(storage:Any,interval_seconds:int=60)->bool:
    global _worker_started
    with _worker_lock:
        if _worker_started:return False
        _worker_started=True
    def loop():
        while True:
            try:
                for row in storage.list_player_audience_rows() if hasattr(storage,"list_player_audience_rows") else []:
                    player=storage.get_player_by_game_id(str(row.get("game_id") or ""))
                    if isinstance(player,dict) and apply_decay(player):storage.update_player(player)
            except Exception:pass
            time.sleep(max(1,int(interval_seconds)))
    threading.Thread(target=loop,name="reputation-decay-worker",daemon=True).start();return True
