"""Published tavern runtime for Telegram/VK (§3–§26)."""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any

from services import tavern_constructor_service as taverns


def _int(value: Any, default: int = 0) -> int:
    try:return int(float(value))
    except (TypeError,ValueError):return default


def _published() -> list[dict[str,Any]]:
    return [env for env in taverns.store().list(status=taverns.STATUS_PUBLISHED) if (env.get("data") or {}).get("tavern_mode","active") not in {"disabled","admin_only"}]


def definition(tavern_id: str) -> dict[str,Any]|None:
    env=next((row for row in _published() if str(row.get("id"))==str(tavern_id)),None)
    return {"id":env.get("id"),**dict(env.get("data") or {})} if env else None


def taverns_for_parent(parent_type: str, parent_id: str, *, platform: str|None=None) -> list[dict[str,Any]]:
    fields={"city":"city_id","fortress":"fortress_id","location":"location_id","sublocation":"sublocation_id","camp":"camp_id"}
    field=fields.get(parent_type);out=[]
    for env in _published():
        data=env.get("data") or {}
        if field and str(data.get(field) or "")==str(parent_id) and data.get("show_in_parent_menu",True):
            if platform=="telegram" and data.get("available_in_telegram") is False:continue
            if platform=="vk" and data.get("available_in_vk") is False:continue
            out.append({"id":env.get("id"),"name":data.get("player_name") or data.get("name") or env.get("id"),"order":_int(data.get("order"))})
    return sorted(out,key=lambda row:(row["order"],row["name"]))


def _inventory_count(player: dict[str,Any], item_id: str) -> int:
    return sum(max(1,_int(row.get("amount"),1)) for row in player.get("inventory") or [] if isinstance(row,dict) and str(row.get("item_id") or row.get("id") or "")==item_id)


def access_error(player: dict[str,Any], data: dict[str,Any], *, now: datetime|None=None) -> str|None:
    denied=str(data.get("access_denied_text") or data.get("closed_text") or "Таверна сейчас недоступна.")
    if data.get("temporarily_closed") or data.get("permanently_closed"):return denied
    if _int(player.get("level"),1)<_int(data.get("required_level")):return denied
    if data.get("required_item_id") and _inventory_count(player,str(data["required_item_id"]))<=0:return denied
    rep_id=str(data.get("required_reputation_id") or "")
    if rep_id and _int((player.get("reputations") or {}).get(rep_id))<_int(data.get("required_reputation_value")):return denied
    hidden=str(data.get("required_hidden_reputation_id") or "")
    if hidden and _int((player.get("hidden_reputations") or {}).get(hidden))<_int(data.get("required_hidden_reputation_value")):return denied
    if data.get("required_quest_id") and str(data["required_quest_id"]) not in ((player.get("quests") or {}).get("completed") or {}):return denied
    if data.get("required_achievement_id") and str(data["required_achievement_id"]) not in {str(x) for x in player.get("achievements") or []}:return denied
    try:
        from services.fine_service import active_fines
        fined=bool(active_fines(player))
    except Exception:fined=False
    if data.get("requires_no_fine") and fined:return denied
    if data.get("requires_fine") and not fined:return denied
    moment=now or datetime.now(timezone.utc);hour=moment.hour
    if data.get("night_only") and not (hour>=20 or hour<6):return denied
    if data.get("day_only") and not 6<=hour<20:return denied
    return None


def _price(player: dict[str,Any], row: dict[str,Any], data: dict[str,Any]) -> int:
    discount=0.0
    for rule in data.get("reputation_rules") or []:
        if not isinstance(rule,dict):continue
        rid=str(rule.get("reputation_id") or "");value=_int((player.get("reputations") or {}).get(rid))
        if _int(rule.get("min_value"),-10**9)<=value<=_int(rule.get("max_value"),10**9):discount+=float(rule.get("price_modifier_percent") or 0)
    base=row.get("price",0)
    if row.get("price_formula_id"):
        try:
            from services.formula_runtime import evaluate
            base=evaluate(row.get("price_formula_id"),{"base_amount":base,"player_level":player.get("level",1),"reputation_discount":discount},default=base)
        except Exception:pass
    result=taverns.final_price(base,reputation_discount_percent=discount,min_price=_int(row.get("min_price")))
    try:
        from services.economy_runtime import service_price
        kind=str(row.get("service_type") or row.get("type") or "tavern")
        return service_price(kind if kind not in {"food","drink","room","rest"} else "tavern",result,player,{"location_id":data.get("location_id"),"sublocation_id":data.get("sublocation_id")})
    except (ImportError,ValueError):return result


def _charge(player: dict[str,Any], amount: int, row: dict[str,Any], data: dict[str,Any]) -> None:
    key="money_copper" if "money_copper" in player else "money"
    if _int(player.get(key))<amount:raise ValueError(str(row.get("error_text") or data.get("not_enough_money_text") or "Недостаточно монет."))
    before=_int(player.get(key));player[key]=before-amount
    if key=="money_copper":player["money"]=player[key]
    try:
        from services.economy_runtime import record
        record(player,"tavern_service","copper",-amount,before,_int(player.get(key)),source="tavern",source_id=str(data.get("id") or ""))
    except (ImportError,OSError):pass


def _restore(player: dict[str,Any], row: dict[str,Any]) -> None:
    for resource in ("hp","mana","spirit","energy"):
        maximum=max(0,_int(player.get(f"max_{resource}"),100));current=_int(player.get(resource))
        flat=_int(row.get(f"restore_{resource}"));percent=float(row.get(f"restore_{resource}_percent") or 0)
        amount=flat+int(maximum*percent/100)
        if row.get("full_restore"):amount=maximum
        player[resource]=min(maximum,current+max(0,amount))
    effect_id=str(row.get("effect_id") or row.get("effect") or "")
    if effect_id:
        from services.effect_formula_runtime import apply_to_player
        apply_to_player(player,effect_id,source="tavern",context={"duration_seconds":row.get("effect_duration_seconds") or row.get("duration_seconds")})


def _rows(data: dict[str,Any], key: str) -> list[dict[str,Any]]:
    return [row for row in data.get(key) or [] if isinstance(row,dict) and row.get("active",row.get("enabled",True))]


def _main(data: dict[str,Any]) -> dict[str,Any]:
    tid=str(data["id"]);buttons=[]
    for key,label,prefix in (("food","Купить еду","food"),("drinks","Купить напиток","drink"),("rest_options","Отдохнуть","rest"),("rooms","Снять комнату","room")):
        if _rows(data,key):buttons.append([f"{label}: {tid}"])
    if _rows(data,"rumors"):buttons.append([f"Послушать слухи: {tid}"])
    if _rows(data,"quests"):buttons.append([f"Задания таверны: {tid}"])
    if _rows(data,"npc_links"):buttons.append([f"NPC таверны: {tid}"])
    for service in _rows(data,"services"):buttons.append([f"Услуга таверны: {tid}:{service.get('service_id') or service.get('id')}"])
    try:
        from services.casino_runtime import casinos_for_parent
        buttons.extend([[row["name"]] for row in casinos_for_parent("tavern",tid)])
    except Exception:pass
    for button in _rows(data,"buttons"):buttons.append([str(button.get("text") or "")])
    buttons.append([str(data.get("return_button_text") or "Назад")])
    return {"text":str(data.get("player_entry_text") or data.get("entry_text") or data.get("description") or data.get("name")),"buttons":buttons,"tavern_id":tid}


def _menu(data: dict[str,Any], key: str, title: str, prefix: str, player: dict[str,Any]) -> dict[str,Any]:
    rows=_rows(data,key);lines=[title];buttons=[]
    for i,row in enumerate(rows,1):
        rid=str(row.get(f"{prefix}_id") or row.get("id") or row.get("food_id") or row.get("drink_id") or row.get("rest_option_id") or row.get("room_id") or i)
        name=str(row.get("player_name") or row.get("name") or rid);price=_price(player,row,data)
        lines.append(f"• {name} — {price} {row.get('currency') or 'copper'}");buttons.append([f"Таверна выбор: {data['id']}:{key}:{rid}"])
    return {"text":"\n".join(lines),"buttons":buttons+[[f"Таверна: {data['id']}"]],"tavern_id":data["id"]}


def _pick(rows: list[dict[str,Any]], key: str, rid: str) -> dict[str,Any]|None:
    aliases=("id",f"{key.rstrip('s')}_id","food_id","drink_id","rest_option_id","room_id","service_id")
    return next((row for row in rows if rid in {str(row.get(k) or "") for k in aliases}),None)


def _event_or_risk(player: dict[str,Any], data: dict[str,Any], trigger: str, rng: random.Random) -> list[str]:
    lines=[]
    for row in [*_rows(data,"events"),*_rows(data,"risks")]:
        if str(row.get("trigger") or "") not in {"",trigger}:continue
        chance=float(row.get("chance_percent") or row.get("base_chance") or 0)
        if rng.random()*100>=chance:continue
        lines.append(str(row.get("player_text") or row.get("risk_text") or row.get("event_text") or "В таверне что-то произошло."))
        if row.get("effect_id"):
            from services.effect_formula_runtime import apply_to_player
            apply_to_player(player,str(row["effect_id"]),source="tavern_risk")
        if row.get("fine_type_id"):
            from services.fine_service import create_raid_fine
            create_raid_fine(player,str(row["fine_type_id"]))
        loss=max(0,_int(row.get("coin_loss")));key="money_copper" if "money_copper" in player else "money";player[key]=max(0,_int(player.get(key))-loss)
    return lines


def try_handle(player: dict[str,Any], action: str, *, platform: str|None=None, rng: random.Random|None=None) -> dict[str,Any]|None:
    rng=rng or random.Random();act=str(action or "").strip();data=None
    for env in _published():
        d={"id":env.get("id"),**dict(env.get("data") or {})};labels={str(env.get("id")),str(d.get("name") or ""),str(d.get("player_name") or ""),str(d.get("entry_button_text") or "")}
        if act in labels:data=d;break
    if act.startswith("Таверна: "):data=definition(act.split(":",1)[1].strip())
    current=str(player.get("current_tavern_id") or "")
    if data:
        denied=access_error(player,data)
        if denied:return {"text":denied,"buttons":[[str(data.get("return_button_text") or "Назад")]]}
        player["current_tavern_id"]=data["id"];response=_main(data);extra=_event_or_risk(player,data,"entry",rng)
        if extra:response["text"]+="\n\n"+"\n".join(extra)
        return response
    data=definition(current)
    if not data:return None
    mappings=(("Купить еду: ","food","🍲 Еда","food"),("Купить напиток: ","drinks","🥤 Напитки","drink"),("Отдохнуть: ","rest_options","🛏 Отдых","rest"),("Снять комнату: ","rooms","🚪 Комнаты","room"))
    for prefix,key,title,item_prefix in mappings:
        if act==prefix+current:return _menu(data,key,title,item_prefix,player)
    if act.startswith("Таверна выбор: "):
        raw=act.removeprefix("Таверна выбор: ");tid,key,rid=raw.split(":",2)
        if tid!=current:return None
        row=_pick(_rows(data,key),key,rid)
        if not row:return {"text":"Пункт меню больше недоступен.","buttons":[[f"Таверна: {current}"]]}
        try:_charge(player,_price(player,row,data),row,data)
        except ValueError as exc:return {"text":str(exc),"buttons":[[f"Таверна: {current}"]]}
        _restore(player,row);text=str(row.get("consume_text") or row.get("success_text") or row.get("enter_text") or data.get("service_success_text") or "Готово.")
        extra=_event_or_risk(player,data,"rest" if key in {"rest_options","rooms"} else "purchase",rng)
        return {"text":text+("\n\n"+"\n".join(extra) if extra else ""),"buttons":[[f"Таверна: {current}"]],"tavern_id":current}
    if act==f"Послушать слухи: {current}":
        candidates=[]
        for row in _rows(data,"rumors"):
            if rng.random()*100<float(row.get("chance_percent") or 100):candidates.append(row)
        row=rng.choice(candidates) if candidates else None
        if not row:return {"text":str(data.get("no_rumor_text") or "Сегодня новых слухов нет."),"buttons":[[f"Таверна: {current}"]]}
        rid=str(row.get("rumor_id") or row.get("id") or "");claims=player.setdefault("tavern_rumor_claims",[])
        if row.get("one_time") and rid in claims:return {"text":str(data.get("no_rumor_text") or "Этот слух вам уже известен."),"buttons":[[f"Таверна: {current}"]]}
        if row.get("one_time"):claims.append(rid)
        for field in ("opens_event_id","opens_quest_id","opens_npc_id","opens_location_id"):
            if row.get(field):player.setdefault("unlocks",{})[str(row[field])]=True
        return {"text":str(row.get("rumor_text")),"buttons":[[f"Таверна: {current}"]],"tavern_id":current}
    if act==f"Задания таверны: {current}":
        rows=_rows(data,"quests");return {"text":str(data.get("quests_text") or "📜 Задания таверны"),"buttons":[[f"Таверна квест: {current}:{row.get('quest_id')}"] for row in rows]+[[f"Таверна: {current}"]]}
    if act.startswith(f"Таверна квест: {current}:"):
        quest_id=act.rsplit(":",1)[1]
        try:
            from services.quest_runtime_service import accept
            result=accept(player,quest_id);text=str(result.get("text"))
        except ValueError as exc:text=str(exc)
        return {"text":text,"buttons":[[f"Таверна: {current}"]]}
    if act==f"NPC таверны: {current}":
        return {"text":str(data.get("npc_text") or "Посетители таверны"),"buttons":[[f"NPC: {row.get('npc_id')}"] for row in _rows(data,"npc_links")]+[[f"Таверна: {current}"]]}
    if act.startswith(f"Услуга таверны: {current}:"):
        rid=act.rsplit(":",1)[1];row=_pick(_rows(data,"services"),"services",rid)
        if not row:return None
        try:_charge(player,_price(player,row,data),row,data)
        except ValueError as exc:return {"text":str(exc),"buttons":[[f"Таверна: {current}"]]}
        kind=str(row.get("service_type") or "")
        if kind=="hire" and row.get("ally_id"):
            from services.npc_ally_runtime import grant
            grant(player,str(row["ally_id"]),source=f"tavern:{current}")
        elif kind=="quest" and row.get("quest_id"):
            from services.quest_runtime_service import accept
            accept(player,str(row["quest_id"]))
        elif kind in {"event","hidden"} and row.get("event_id"):player["constructor_event_id"]=str(row["event_id"])
        elif kind=="custom" and row.get("target_location_id"):player.update({"current_location":row["target_location_id"],"location_id":row["target_location_id"]})
        elif kind=="casino":player["current_casino_id"]=str(row.get("casino_id") or data.get("casino_id") or "underground")
        _restore(player,row)
        buttons=[[f"Казино: {player.get('current_casino_id')}"]] if kind=="casino" else [[f"Таверна: {current}"]]
        return {"text":str(row.get("success_text") or "Услуга оказана."),"buttons":buttons}
    for button in _rows(data,"buttons"):
        if act!=str(button.get("text") or ""):continue
        kind=str(button.get("action_type") or "");target=str(button.get("target_id") or "")
        if kind in {"casino","open_casino","underground"}:player["current_casino_id"]=target or str(data.get("casino_id") or "underground")
        elif kind in {"goto_location","return"}:player.update({"current_location":target,"location_id":target});player.pop("current_tavern_id",None)
        return {"text":str(button.get("success_text") or data.get("transition_text") or "Переход выполнен."),"buttons":[],"route":{"kind":kind,"id":target}}
    return None
