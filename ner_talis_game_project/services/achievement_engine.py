"""Achievement engine — runtime: прогресс, выдача, ручная выдача/откат.

Работает поверх опубликованных достижений из achievement_service и состояния
игрока ``player["achievements"]``. Игровой код вызывает ``record_progress`` при
действиях игрока (kill_mob, reach_level, ...); движок обновляет прогресс и
выдаёт достижение при выполнении условий. Ручная выдача/откат — для админа.

Состояние игрока:
    player["achievements"] = {
        "earned":   { ach_id: {at, source, by, reason} },
        "progress": { ach_id: {"counts": {cond_index: number}} },
        "history":  [ {ach_id, at, source, by, reason, reward_status} ]  # capped
    }
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services import achievement_service as ach

_HISTORY_CAP = 500


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _state(player: dict[str, Any]) -> dict[str, Any]:
    state = player.get("achievements")
    if not isinstance(state, dict):
        state = {"earned": {}, "progress": {}, "history": []}
        player["achievements"] = state
    state.setdefault("earned", {})
    state.setdefault("progress", {})
    state.setdefault("history", [])
    return state


def is_earned(player: dict[str, Any], ach_id: str) -> bool:
    return str(ach_id) in _state(player).get("earned", {})


def _published() -> list[dict[str, Any]]:
    return ach.store().list(status=ach.STATUS_PUBLISHED)


def _conditions(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("conditions")
    return [c for c in raw if isinstance(c, dict)] if isinstance(raw, list) else []


def _period_key(period: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc); period = str(period or "all")
    if period == "day": return now.strftime("%Y-%m-%d")
    if period == "week":
        year, week, _ = now.isocalendar(); return f"{year}-W{week:02d}"
    if period == "month": return now.strftime("%Y-%m")
    if period == "season": return f"{now.year}-Q{((now.month - 1) // 3) + 1}"
    return "all"


def _count_key(index: int, condition: dict[str, Any]) -> str:
    period = str(condition.get("period") or "all")
    if period == "event": return f"{index}:event:{condition.get('event_id') or condition.get('target') or 'current'}"
    return str(index) if period in ("", "all", "forever") else f"{index}:{period}:{_period_key(period)}"


def _repeat_key(data: dict[str, Any]) -> str:
    period = str(data.get("repeat_period") or "").strip()
    return _period_key(period) if period else ""


def _evaluate(data: dict[str, Any], counts: dict[str, Any]) -> bool:
    """Выполнено ли достижение по текущему прогрессу и логике условий."""
    conditions = _conditions(data)
    if not conditions:
        return False
    met: list[tuple[dict[str, Any], bool]] = []
    for idx, cond in enumerate(conditions):
        raw_current=counts.get(_count_key(idx,cond));current = _num(raw_current, 0)
        threshold = _num(cond.get("amount", cond.get("value", cond.get("minimum", 1))), 1)
        operator = str(cond.get("operator") or "gte").lower()
        if operator in ("eq", "equal", "равно"):
            ok = current == threshold
        elif operator in ("ne", "not_equal", "не равно"):
            ok = current != threshold
        elif operator in ("gt", "greater", "больше"):
            ok = current > threshold
        elif operator in ("lt", "less", "меньше"):
            ok = current < threshold
        elif operator in ("lte", "less_or_equal", "меньше или равно"):
            ok = current <= threshold
        elif operator in ("between", "между"):
            ok = _num(cond.get("minimum"), threshold) <= current <= _num(cond.get("maximum"), threshold)
        elif operator in ("contains", "содержит"):
            needle=str(cond.get("value") or cond.get("target") or "");ok=needle in ({str(x) for x in raw_current} if isinstance(raw_current,list) else str(raw_current or ""))
        elif operator in ("not_contains", "не содержит"):
            needle=str(cond.get("value") or cond.get("target") or "");ok=needle not in ({str(x) for x in raw_current} if isinstance(raw_current,list) else str(raw_current or ""))
        elif operator in ("not_completed", "not_received", "inactive", "не выполнено", "не получено", "неактивно"):
            ok = current < threshold
        else:  # gte/completed/received/active
            ok = current >= threshold
        met.append((cond, ok))
    logic = str(data.get("condition_logic") or "all")
    if logic == "any":
        return any(ok for _, ok in met)
    if logic == "n_of":
        need = int(_num(data.get("condition_n"), len(met)))
        return sum(1 for _, ok in met if ok) >= max(1, need)
    primary = [ok for cond, ok in met if cond.get("required") is not False and not cond.get("alternative")]
    alternatives = [ok for cond, ok in met if cond.get("alternative")]
    # all / ordered: обязательные нужны все, из альтернативных — хотя бы одна.
    return all(primary) and (not alternatives or any(alternatives))


# --- Применение наград ------------------------------------------------------
_REWARD_KIND = {
    "experience": "experience", "exp_grains": "experience",
    "coins": "money", "stat_points": "stat_points", "skill_points": "skill_points",
    "item": "item", "unique_item": "item",
}
_COSMETIC = {"title", "emblem", "profile_icon", "passive_bonus"}


def apply_rewards(player: dict[str, Any], rewards: Any) -> tuple[list[str], list[str]]:
    """Выдать награды достижения игроку. Возвращает (строки, ошибки)."""
    if not isinstance(rewards, list):
        return [], []
    lines: list[str] = []
    errors: list[str] = []
    mapped: list[dict[str, Any]] = []
    for rw in rewards:
        if not isinstance(rw, dict):
            continue
        rtype = str(rw.get("type") or "").strip()
        amount = int(_num(rw.get("amount"), 1)) or 1
        if rtype in _REWARD_KIND:
            kind = _REWARD_KIND[rtype]
            item_id = "money_copper" if kind == "money" else (str(rw.get("item_id") or "") or rtype)
            if kind == "money":
                try:
                    from services.economy_runtime import reward_amount
                    amount = reward_amount("achievement", amount, {"player_level": player.get("level", 1)})
                except (ImportError, ValueError):
                    pass
            mapped.append({"item_id": item_id, "amount": amount, "kind": kind})
        elif rtype == "title":
            titles = player.setdefault("titles", [])
            tid = str(rw.get("title_id") or rw.get("item_id") or "").strip()
            if tid and not any((isinstance(t, dict) and t.get("id") == tid) or t == tid for t in titles):
                titles.append({"id":tid,"name":rw.get("title_name") or tid,"description":rw.get("title_description") or "","source_achievement":rw.get("source_achievement"),"stage_id":rw.get("stage_id"),"show_profile":rw.get("show_profile",True),"show_rating":bool(rw.get("show_rating")),"show_messages":bool(rw.get("show_messages")),"can_enable":rw.get("can_enable",True),"can_disable":rw.get("can_disable",True),"active":bool(rw.get("active_by_default")),"rarity":rw.get("rarity"),"color":rw.get("color"),"icon":rw.get("icon")})
            lines.append(f"Титул: {rw.get('title_name') or tid}")
        elif rtype in _COSMETIC:
            bucket = player.setdefault("achievement_rewards", {}).setdefault(rtype, [])
            bucket.append(rw)
            lines.append(rtype)
        elif rtype == "temp_buff":
            effect_id = str(rw.get("effect_id") or rw.get("item_id") or "").strip()
            from services.effect_formula_runtime import apply_to_player
            apply_to_player(player, effect_id, source="achievement", context={"duration_seconds": int(_num(rw.get("duration_seconds"), 0))})
            lines.append(f"Эффект: {effect_id}")
        elif rtype == "effect":
            effect_id=str(rw.get("effect_id") or rw.get("object_id") or rw.get("item_id") or "")
            from services.effect_formula_runtime import apply_to_player
            apply_to_player(player,effect_id,source="achievement",context={"duration_seconds":int(_num(rw.get("duration_seconds"),0)),"permanent":bool(rw.get("permanent"))});lines.append(f"Эффект: {effect_id}")
        elif rtype == "skill":
            skill_id=str(rw.get("skill_id") or rw.get("object_id") or rw.get("item_id") or "")
            if skill_id:
                player.setdefault("unlocked_skills",[])
                if skill_id not in player["unlocked_skills"]:player["unlocked_skills"].append(skill_id)
                player.setdefault("achievement_skill_rules",{})[skill_id]={"temporary":bool(rw.get("temporary")),"expires_at":rw.get("expires_at"),"can_upgrade":rw.get("can_upgrade",True),"activation_required":bool(rw.get("activation_required"))};lines.append(f"Навык: {skill_id}")
        elif rtype.startswith("unlock_"):
            object_id = str(rw.get("object_id") or rw.get("item_id") or "").strip()
            if object_id:
                player.setdefault("unlocks", {})[object_id] = True
                lines.append(f"Открыто: {object_id}")
        elif rtype == "guild_points":
            player["guild_points"] = int(_num(player.get("guild_points"))) + amount
            lines.append(f"Очки гильдии: +{amount}")
        elif rtype == "event_currency":
            currency_id = str(rw.get("currency_id") or rw.get("item_id") or "event")
            currencies = player.setdefault("event_currencies", {})
            currencies[currency_id] = int(_num(currencies.get(currency_id))) + amount
            lines.append(f"Валюта события: +{amount}")
        elif rtype in {"reputation","hidden_reputation"}:
            rid=str(rw.get("reputation_id") or rw.get("object_id") or "");bucket=player.setdefault("hidden_reputations" if rtype=="hidden_reputation" else "reputations",{});bucket[rid]=int(_num(bucket.get(rid)))+amount;lines.append(f"Репутация {rid}: {amount:+d}")
        elif rtype in {"discount","sale_bonus","commission_relief","free_service","fine_reduction"}:
            key=str(rw.get("object_id") or rw.get("service_id") or rw.get("market_id") or "global");player.setdefault("achievement_economy_bonuses",{}).setdefault(rtype,{})[key]={"value":amount,"percent":rw.get("percent"),"limit":rw.get("limit"),"expires_at":rw.get("expires_at")};lines.append(str(rw.get("text") or f"Экономический бонус: {rtype}"))
        elif rtype == "special_button":
            player.setdefault("achievement_buttons",[]).append({"id":rw.get("button_id") or rw.get("object_id"),"label":rw.get("label"),"action":rw.get("action")});lines.append(str(rw.get("text") or "Открыта особая кнопка"))
        elif rtype == "hidden_description":
            player.setdefault("revealed_achievement_descriptions",[]).append(str(rw.get("object_id") or rw.get("achievement_id") or ""));lines.append(str(rw.get("text") or "Открыто скрытое описание"))
        elif rtype == "system_flag":
            player.setdefault("system_flags",{})[str(rw.get("object_id") or rw.get("flag") or "")]=rw.get("value",True);lines.append(str(rw.get("text") or "Установлен системный флаг"))
        elif rtype in {"npc_helper", "npc_ally"}:
            ally_id = str(rw.get("object_id") or rw.get("ally_id") or rw.get("item_id") or "").strip()
            if ally_id:
                from services.npc_ally_runtime import grant
                grant(player, ally_id, source="achievement")
                lines.append(f"NPC-помощник: {ally_id}")
        else:
            # unlock_*/guild_points/event_currency/temp_buff — нужен отдельный
            # runtime; фиксируем как отложенную награду.
            player.setdefault("achievement_rewards", {}).setdefault("pending", []).append(rw)
    if mapped:
        try:
            from services.admin_panel_service import _apply_rewards_to_player
            lines.extend(_apply_rewards_to_player(player, mapped, source="achievement"))
        except Exception as exc:  # нет места в инвентаре и т.п.
            errors.append(str(exc))
    return lines, errors


def _notify(storage: Any, player: dict[str, Any], data: dict[str, Any], lines: list[str]) -> None:
    game_id = player.get("game_id") or player.get("id")
    if not game_id:
        return
    hidden = str(data.get("visibility") or "") in ("hidden_until_earned", "fully_hidden")
    name = data.get("name") or "Достижение"
    desc = data.get("short_description") or data.get("description") or ""
    header = "🏆 Скрытое достижение открыто!" if hidden else "🏆 Достижение получено!"
    text = f"{header}\n\n{name}"
    if desc:
        text += f"\n{desc}"
    if lines:
        text += "\n\nНаграда:\n" + "\n".join(f"• {line}" for line in lines)
    message = {"type": "achievement", "text": text, "created_at": _now_iso(), "source": "achievement"}
    ach_id = data.get("id") or ""
    from services.message_delivery import notify_player
    status = notify_player(
        storage, game_id, text, type="achievement", priority="high",
        delivery_key=(f"achievement:{ach_id}:{game_id}" if ach_id else None),
        source="achievement", fallback_message=message,
        text_key="achievement.earned", text_variables={"name": name},
    )
    if status == "skipped":
        player.setdefault("pending_bot_messages", []).append(message)


def _append_history(state: dict[str, Any], entry: dict[str, Any]) -> None:
    history = state.setdefault("history", [])
    history.append(entry)
    if len(history) > _HISTORY_CAP:
        del history[:-_HISTORY_CAP]

def _award_stages(player:dict[str,Any],ach_id:str,data:dict[str,Any],progress:dict[str,Any],counts:dict[str,Any])->list[str]:
    awarded=progress.setdefault("awarded_stages",[]);messages=[];current=max([_num(value) for value in counts.values()] or [0])
    for index,stage in enumerate(data.get("stages") or [],1):
        if not isinstance(stage,dict):continue
        sid=str(stage.get("stage_id") or stage.get("number") or index);required=_num(stage.get("required_progress",stage.get("required_value")),0)
        if sid in awarded or current<required:continue
        rewards=list(stage.get("rewards") or stage.get("reward") or [])
        if isinstance(stage.get("reward"),dict):rewards=[stage["reward"]]
        for field,rtype,key in (("title","title","title_id"),("effect","effect","effect_id"),("skill","skill","skill_id")):
            value=stage.get(field) or stage.get(f"{field}_id")
            if value:rewards.append({"type":rtype,key:value,"object_id":value,"permanent":stage.get("permanent",True),"source_achievement":ach_id,"stage_id":sid,"title_name":stage.get("title_name") or value})
        apply_rewards(player,rewards);player["achievement_points"]=int(_num(player.get("achievement_points")))+int(_num(stage.get("achievement_points"),0));awarded.append(sid)
        messages.append(str(stage.get("receive_text") or stage.get("text") or f"Открыта стадия достижения: {stage.get('name') or sid}."))
    if messages:player.setdefault("pending_bot_messages",[]).append({"type":"achievement_stage","achievement_id":ach_id,"text":"\n".join(messages),"created_at":_now_iso()})
    return messages


def grant(
    storage: Any,
    player: dict[str, Any],
    ach_id: str,
    *,
    source: str = "auto",
    by: str = "",
    reason: str = "",
    save: bool = True,
    notify: bool = True,
) -> bool:
    """Выдать достижение игроку (идемпотентно, если не повторяемое)."""
    ach_id = str(ach_id)
    envelope = ach.store().get(ach_id)
    if envelope is None:
        raise ValueError(f"Достижение {ach_id} не найдено.")
    data = envelope.get("data") or {}
    state = _state(player)
    repeatable = bool(data.get("repeatable"))
    if ach_id in state["earned"]:
        repeat_key = _repeat_key(data)
        if not repeatable or (repeat_key and state["earned"][ach_id].get("period_key") == repeat_key):
            return False
    lines, errors = apply_rewards(player, data.get("rewards"))
    player["achievement_points"]=int(_num(player.get("achievement_points")))+int(_num(data.get("achievement_points"),0))
    reward_status = "error" if errors else "ok"
    state["earned"][ach_id] = {
        "at": _now_iso(), "source": source, "by": str(by or ""), "reason": str(reason or ""),
        "period_key": _repeat_key(data),
    }
    _append_history(state, {
        "ach_id": ach_id, "at": _now_iso(), "source": source,
        "by": str(by or ""), "reason": str(reason or ""),
        "reward_status": reward_status, "reward_errors": errors,
    })
    try:
        from services.reputation_runtime_service import apply_trigger
        apply_trigger(player, "achievement", ach_id)
    except Exception:
        pass
    if notify:
        _notify(storage, player, data, lines)
    if save:
        storage.update_player(player)
    return True


def revoke(storage: Any, player: dict[str, Any], ach_id: str, *, by: str = "", reason: str = "", save: bool = True) -> bool:
    """Откатить выданное достижение (награды не возвращаются)."""
    ach_id = str(ach_id)
    state = _state(player)
    if ach_id not in state["earned"]:
        return False
    state["earned"].pop(ach_id, None)
    state["progress"].pop(ach_id, None)
    _append_history(state, {
        "ach_id": ach_id, "at": _now_iso(), "source": "manual_revoke",
        "by": str(by or ""), "reason": str(reason or ""), "reward_status": "revoked",
    })
    if save:
        storage.update_player(player)
    return True


def record_progress(
    storage: Any,
    player: dict[str, Any],
    event_type: str,
    amount: float = 1,
    target: str | None = None,
    *,
    save: bool = True,
) -> list[str]:
    """Хук игрового действия. Обновляет прогресс и выдаёт готовые достижения.

    Возвращает список id только что выданных достижений.
    """
    state = _state(player)
    newly: list[str] = []
    changed = False
    for envelope in _published():
        ach_id = str(envelope.get("id"))
        data = envelope.get("data") or {}
        if ach_id in state["earned"] and not bool(data.get("repeatable")):
            continue
        repeat_key = _repeat_key(data)
        if bool(data.get("repeatable")) and repeat_key and ach_id in state["earned"] and state["earned"][ach_id].get("period_key") == repeat_key:
            continue
        conditions = _conditions(data)
        matched = False
        progress_state=state["progress"].setdefault(ach_id, {});counts = progress_state.setdefault("counts", {})
        reveal_match=(
            (data.get("reveal_npc_id") and event_type in {"visit_npc","talk_npc"} and str(target)==str(data.get("reveal_npc_id")))
            or (data.get("reveal_item_id") and event_type in {"find_item","use_item"} and str(target)==str(data.get("reveal_item_id")))
            or (data.get("reveal_event_id") and event_type in {"finish_event","join_world_event"} and str(target)==str(data.get("reveal_event_id")))
        )
        if reveal_match:progress_state["revealed"]=True;changed=True
        if (event_type=="death" and data.get("reset_on_death")) or (event_type=="finish_event" and data.get("reset_on_event_end")) or (event_type=="season_end" and data.get("reset_on_season_end")):
            counts.clear();progress_state["awarded_stages"]=[];changed=True
        ordered = str(data.get("condition_logic") or "all") == "ordered"
        first_unmet = next((idx for idx, cond in enumerate(conditions) if _num(counts.get(_count_key(idx, cond)), 0) < (_num(cond.get("amount"), 1) or 1)), None)
        for idx, cond in enumerate(conditions):
            if ordered and first_unmet is not None and idx != first_unmet:
                continue
            if str(cond.get("type") or "") != str(event_type):
                continue
            ctarget = str(cond.get("target") or "").strip()
            if ctarget and ctarget != str(target or ""):
                continue
            if str(cond.get("operator") or "") in {"contains","not_contains"}:
                key=_count_key(idx,cond);values=counts.setdefault(key,[])
                if not isinstance(values,list):values=[];counts[key]=values
                if target is not None and str(target) not in {str(x) for x in values}:values.append(str(target))
            elif str(event_type) in {"reach_level", "gain_currency", "reputation", "hidden_reputation", "no_warnings_days"}:
                key = _count_key(idx, cond)
                counts[key] = max(_num(counts.get(key), 0), _num(amount, 0))
            else:
                key = _count_key(idx, cond)
                counts[key] = _num(counts.get(key), 0) + _num(amount, 1)
            matched = True
        if matched:
            changed = True
            if data.get("reveal_after_first_progress"):progress_state["revealed"]=True
            _award_stages(player,ach_id,data,progress_state,counts)
            if _evaluate(data, counts):
                grant(storage, player, ach_id, source="auto", save=False)
                newly.append(ach_id)
                if bool(data.get("repeatable")):
                    state["progress"][ach_id]["counts"] = {}
    if changed and save:
        storage.update_player(player)
    return newly


def record_game_event(player: dict[str, Any], event_type: str, amount: float = 1,
                      target: str | None = None, *, storage: Any = None) -> list[str]:
    """Безопасный runtime-хук для общих сервисов до/вне сохранения игрока."""
    item_trigger = {"gather_resource": "on_gather"}.get(str(event_type))
    if item_trigger:
        try:
            from services.item_effect_trigger_runtime import trigger_owned
            trigger_owned(player, item_trigger, context={"item_count": amount, "object_id": target or "", "location_id": target or ""})
        except Exception:
            pass
    return record_progress(storage, player, event_type, amount, target, save=False)


# --- Представления ----------------------------------------------------------
def _progress_summary(data: dict[str, Any], counts: dict[str, Any]) -> str:
    conditions = _conditions(data)
    if not conditions:
        return ""
    def current(idx,cond):return max([_num(value) for key,value in counts.items() if str(key)==str(idx) or str(key).startswith(f"{idx}:")] or [0])
    done = sum(1 for idx, c in enumerate(conditions) if current(idx,c) >= (_num(c.get("amount"), 1) or 1))
    if len(conditions) == 1:
        threshold = int(_num(conditions[0].get("amount"), 1) or 1)
        value = int(current(0,conditions[0]))
        return f"{min(value, threshold)} / {threshold}"
    return f"{done} / {len(conditions)} условий"


def player_view(player: dict[str, Any]) -> dict[str, Any]:
    """Для профиля игрока (ТЗ §21): без формул/ID, скрытые как ???."""
    state = _state(player)
    earned_ids = set(state.get("earned", {}))
    earned: list[dict[str, Any]] = []
    in_progress: list[dict[str, Any]] = []
    for envelope in _published():
        ach_id = str(envelope.get("id"))
        data = envelope.get("data") or {}
        visibility = str(data.get("visibility") or "open");progress_state=state.get("progress",{}).get(ach_id,{})
        if visibility == "admin":
            continue
        if ach_id in earned_ids:
            earned.append({
                "name": data.get("name"), "description": data.get("short_description") or data.get("description"),
                "rarity": data.get("rarity"), "category": data.get("category"),
                "at": state["earned"][ach_id].get("at"),
            })
            continue
        revealed=bool(progress_state.get("revealed"));fully_hidden=visibility=="fully_hidden" or data.get("hide_until_earned")
        if fully_hidden and not revealed:
            continue
        counts = progress_state.get("counts", {})
        if (visibility == "hidden_until_earned" or data.get("hidden") or data.get("secret")) and not revealed:
            in_progress.append({"name": "???" if data.get("show_as_question",True) else data.get("player_name") or data.get("name"), "description":data.get("hint") if data.get("show_hint") else "", "hidden": True, "progress": "" if data.get("hide_progress") else _progress_summary(data, counts) if counts else ""})
        else:
            in_progress.append({
                "name": data.get("name"), "description": data.get("short_description"),
                "rarity": data.get("rarity"), "category": data.get("category"),
                "progress": "" if data.get("hide_progress") or data.get("show_progress") is False else _progress_summary(data, counts),
            })
    return {"earned": earned, "inProgress": in_progress, "earnedCount": len(earned)}


def admin_player_progress(player: dict[str, Any]) -> dict[str, Any]:
    """Полная картина для админа (включая скрытые/служебные, прогресс, историю)."""
    state = _state(player)
    earned_ids = set(state.get("earned", {}))
    rows: list[dict[str, Any]] = []
    for envelope in _published():
        ach_id = str(envelope.get("id"))
        data = envelope.get("data") or {}
        counts = state.get("progress", {}).get(ach_id, {}).get("counts", {})
        rows.append({
            "id": ach_id, "name": data.get("name"), "rarity": data.get("rarity"),
            "visibility": data.get("visibility"), "category": data.get("category"),
            "earned": ach_id in earned_ids,
            "earnedAt": state["earned"].get(ach_id, {}).get("at"),
            "source": state["earned"].get(ach_id, {}).get("source"),
            "progress": _progress_summary(data, counts),
        })
    rows.sort(key=lambda r: (not r["earned"], str(r.get("name") or "")))
    return {"achievements": rows, "history": list(reversed(state.get("history", [])))[:100]}
