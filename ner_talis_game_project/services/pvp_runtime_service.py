"""Минимальный полноценный runtime PVP: вызов, согласие, ходы и завершение.

Состояние хранится в JSON, поэтому вызовы переживают рестарт web/bot-процесса.
Мутации игроков выполняются через переданное storage. Посмертные проклятия
помечаются source=pvp_player_death — прочие смерти сюда попасть не могут.
"""
from __future__ import annotations
import json, os, random, threading, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from project_paths import resolve_project_path
from services.pvp_constructor_service import active_rule
from services.combat_constructor_service import resolve_profile

_lock = threading.RLock()
def _path() -> Path: return resolve_project_path(os.getenv("PVP_SESSIONS_PATH", "data/pvp_sessions.json"))
def _load() -> dict[str, Any]:
    try:
        data=json.loads(_path().read_text(encoding="utf-8")); return data if isinstance(data,dict) else {}
    except (OSError,json.JSONDecodeError): return {}
def _save(data: dict[str,Any]) -> None:
    path=_path(); path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(path)
def _now() -> str: return datetime.now(timezone.utc).isoformat()
def _gid(p: dict[str,Any]) -> str: return str(p.get("game_id") or p.get("id") or "")
def _hp(p: dict[str,Any]) -> int: return max(1,int(p.get("hp") or (p.get("stats") or {}).get("hp") or 100))
def _text(rule: dict[str,Any], key: str, default: str, **values: Any) -> str:
    authored=next((row.get("text") for row in rule.get("texts") or [] if isinstance(row,dict) and row.get("key")==key),None)
    try:return str(authored or default).format_map(values)
    except (KeyError,ValueError):return str(authored or default)

def render_session(session: dict[str,Any], viewer_id: str="") -> str:
    rule=session.get("rule") or {}; participants=session.get("participants") or {}; me=participants.get(viewer_id) or {}; other_id=session.get("opponent") if viewer_id==session.get("challenger") else session.get("challenger"); other=participants.get(other_id) or {}
    values={"player":viewer_id,"opponent":other_id,"hp":me.get("hp"),"max_hp":me.get("max_hp"),"enemy_hp":other.get("hp"),"enemy_max_hp":other.get("max_hp"),"round":session.get("round",1),"turn":session.get("turn"),"log":"\n".join(str(row.get("text") or "") for row in session.get("log") or [])}
    layout=str(rule.get("message_layout") or "").strip()
    if layout:
        for row in rule.get("message_blocks") or []:
            if isinstance(row,dict): values[str(row.get("block") or "")]=("" if row.get("enabled") is False else str(row.get("template") or "").format_map(values))
        try:return layout.format_map(values)
        except (KeyError,ValueError):pass
    return f"⚔️ PVP · ход {values['round']}\n{viewer_id}: {values['hp']}/{values['max_hp']} HP\n{other_id}: {values['enemy_hp']}/{values['enemy_max_hp']} HP\n{values['log']}"

def create_challenge(challenger: dict[str,Any], opponent: dict[str,Any], *, pvp_type: str="duel", location_id: str="",
                     challenger_allies: list[dict[str,Any]]|None=None, opponent_allies: list[dict[str,Any]]|None=None) -> dict[str,Any]:
    a,b=_gid(challenger),_gid(opponent)
    if not a or not b or a==b: raise ValueError("Нужны два разных зарегистрированных игрока.")
    try:
        from services.world_event_runtime import multiplier
        if multiplier("pvp_chance_multiplier",context={"location_id":location_id,"game_id":a,"object_id":pvp_type})<=0:raise ValueError("PVP временно недоступен из-за мирового события.")
    except ValueError:raise
    except Exception:pass
    rule=active_rule(pvp_type,location_id)
    if not rule: raise ValueError("Для этого типа PVP нет опубликованного правила.")
    min_level=int(rule.get("min_level") or 0)
    if int(challenger.get("level") or 1)<min_level or int(opponent.get("level") or 1)<min_level: raise ValueError("Игрок не достиг минимального уровня PVP.")
    diff=int(rule.get("max_level_diff") or 0)
    if diff and abs(int(challenger.get("level") or 1)-int(opponent.get("level") or 1))>diff: raise ValueError("Слишком большая разница уровней.")
    profile=resolve_profile("pvp",object_id=str(rule.get("id") or ""),group_battle=bool(challenger_allies or opponent_allies or rule.get("sides")))
    challenger_allies=list(challenger_allies or []); opponent_allies=list(opponent_allies or [])
    if (challenger_allies or opponent_allies) and rule.get("allow_player_allies") is False: raise ValueError("Игроки-союзники запрещены этим правилом PVP.")
    all_ids=[_gid(row) for row in [challenger,opponent,*challenger_allies,*opponent_allies]]
    if any(not gid for gid in all_ids) or len(set(all_ids)) != len(all_ids):
        raise ValueError("Участники PVP-групп должны быть зарегистрированы и не могут повторяться на сторонах.")
    player_limit=int(profile.get("max_players") or rule.get("max_players_per_side") or 0)
    player_limit=int(rule.get("max_player_allies") or player_limit)
    if player_limit and (1+len(challenger_allies)>player_limit or 1+len(opponent_allies)>player_limit):
        raise ValueError("Превышен лимит игроков на стороне PVP.")
    from services.combat_group_runtime import pvp_allies
    try:
        from services.npc_ally_runtime import battle_snapshots
        active_a=battle_snapshots(challenger,mode="pvp"); active_b=battle_snapshots(opponent,mode="pvp")
    except Exception:
        active_a=[]; active_b=[]
    authored_npc=[row for row in rule.get("npc_allies") or [] if isinstance(row,dict)]
    def npc_rows(side: str, active: list[dict[str,Any]]) -> list[dict[str,Any]]:
        result=list(active)
        for row in authored_npc:
            if str(row.get("side") or "challenger")!=side:continue
            level=max(1,int(row.get("level") or 1));result.append({"participant_id":row.get("npc_id"),"source_id":row.get("combat_npc_id") or row.get("npc_id"),"name":row.get("name") or row.get("npc_id"),"hp":row.get("hp") or level*30,"damage":row.get("damage") or level*5,"behavior":row.get("behavior") or "auto"})
        return result
    sid=uuid.uuid4().hex; session={"id":sid,"state":"pending","rule_id":rule["id"],"rule":rule,"combat_profile":profile,"location_id":location_id,
        "challenger":a,"opponent":b,"created_at":_now(),"participants":{a:{"hp":_hp(challenger),"max_hp":_hp(challenger),"defending":False,"skips":0,"level":int(challenger.get("level") or 1),"initiative":int(challenger.get("initiative") or challenger.get("agility") or 0),"achievements":list((challenger.get("achievements") or {}).keys()) if isinstance(challenger.get("achievements"),dict) else list(challenger.get("achievements") or [])},b:{"hp":_hp(opponent),"max_hp":_hp(opponent),"defending":False,"skips":0,"level":int(opponent.get("level") or 1),"initiative":int(opponent.get("initiative") or opponent.get("agility") or 0),"achievements":list((opponent.get("achievements") or {}).keys()) if isinstance(opponent.get("achievements"),dict) else list(opponent.get("achievements") or [])}},"log":[]}
    session["allies"]={a:pvp_allies(profile,a,"challenger",challenger_allies,npc_rows("challenger",active_a)),b:pvp_allies(profile,b,"opponent",opponent_allies,npc_rows("opponent",active_b))}
    with _lock: all_=_load(); all_[sid]=session; _save(all_)
    return session

def get_session(session_id: str) -> dict[str,Any]|None:
    with _lock: value=_load().get(session_id); return dict(value) if isinstance(value,dict) else None
def _put(session: dict[str,Any]) -> dict[str,Any]:
    with _lock: all_=_load(); all_[session["id"]]=session; _save(all_); return session

def respond(session_id: str, player_id: str, accept: bool) -> dict[str,Any]:
    s=get_session(session_id)
    if not s or s.get("state")!="pending": raise ValueError("PVP-вызов не найден или уже обработан.")
    if str(player_id)!=s["opponent"]: raise PermissionError("Ответить может только вызванный игрок.")
    if not accept: s["state"]="declined"; s["finished_at"]=_now(); return _put(s)
    s["state"]="active";s["round"]=1;s["started_at"]=_now();rule=s.get("rule") or {};order=str(rule.get("action_order") or "sequential")
    if order in {"side_a_first","sequential","alternate_sides"}:s["turn"]=s["challenger"]
    elif order in {"defender_first","side_b_first"}:s["turn"]=s["opponent"]
    elif order=="random":s["turn"]=random.Random(str(s.get("id"))).choice([s["challenger"],s["opponent"]])
    elif order in {"by_initiative","by_speed"}:s["turn"]=max((s["challenger"],s["opponent"]),key=lambda pid:int(s["participants"][pid].get("initiative") or 0))
    elif order=="by_level":s["turn"]=max((s["challenger"],s["opponent"]),key=lambda pid:int(s["participants"][pid].get("level") or 1))
    else:s["turn"]=s["challenger"]
    profile=s.get("combat_profile") or resolve_profile("pvp",object_id=str(s.get("rule_id") or ""),group_battle=False)
    s["turn_seconds"]=int(s["rule"].get("turn_seconds") or profile.get("turn_seconds") or 100); s["on_timeout"]=s["rule"].get("on_timeout") or profile.get("on_timeout") or "skip"
    return _put(s)

def act(session_id: str, player_id: str, action: str, *, rng: random.Random|None=None) -> dict[str,Any]:
    s=get_session(session_id)
    if not s or s.get("state")!="active": raise ValueError("PVP-бой не активен.")
    pid=str(player_id)
    if s.get("turn")!=pid: raise PermissionError("Сейчас ход другого игрока.")
    other=s["opponent"] if pid==s["challenger"] else s["challenger"]; me=s["participants"][pid]; target=s["participants"][other]
    enemy_allies=[row for row in (s.get("allies") or {}).get(other) or [] if isinstance(row,dict) and int(row.get("current_hp") or row.get("hp") or 0)>0]
    if int(target.get("hp") or 0)<=0 and enemy_allies:target=enemy_allies[0]
    def side_defeated() -> bool:return int(s["participants"][other].get("hp") or 0)<=0 and not any(int(row.get("current_hp") or row.get("hp") or 0)>0 for row in (s.get("allies") or {}).get(other) or [] if isinstance(row,dict))
    rule=s.get("rule") or {}; configured=next((row for row in rule.get("actions") or [] if isinstance(row,dict) and row.get("action")==action),None)
    if configured and configured.get("enabled") is False: raise ValueError("Это действие запрещено правилом PVP.")
    if action=="surrender":
        if rule.get("surrender_allowed") is False: raise ValueError("Сдача в этом PVP запрещена.")
        target["hp"]=max(1,target["hp"]); return _finish(s,winner=other,loser=pid,reason="surrender",rng=rng)
    if action=="defend": me["defending"]=True; text=f"{pid} защищается."
    elif action=="attack":
        r=rng or random.Random(); base=max(1,int(s["rule"].get("base_damage") or 10)); damage=max(1,base+r.randint(-2,2));
        if target.get("defending"): damage=max(1,damage//2); target["defending"]=False
        hp_key="current_hp" if "current_hp" in target else "hp";target[hp_key]=max(0,int(target.get(hp_key) or 0)-damage); text=f"{pid} наносит {damage} урона {target.get('name') or other}."
        if side_defeated(): s["log"].append({"at":_now(),"text":text}); return _finish(s,winner=pid,loser=other,reason="death",rng=rng)
        from services.combat_group_runtime import pvp_ally_attacks
        ally_log=pvp_ally_attacks((s.get("allies") or {}).get(pid) or [],target,r)
        text += (" " + " ".join(ally_log)) if ally_log else ""
        if side_defeated(): s["log"].append({"at":_now(),"text":text}); return _finish(s,winner=pid,loser=other,reason="death",rng=rng)
    elif action=="flee":
        if rule.get("flee_allowed") is False: raise ValueError("Побег в этом PVP запрещён.")
        chance=float(rule.get("flee_chance") if rule.get("flee_chance") is not None else 100)
        if rule.get("flee_formula_id"):
            from services.formula_runtime import evaluate
            chance=float(evaluate(rule["flee_formula_id"],{"round":s.get("round",1),"current_hp":me.get("hp",0),"max_hp":me.get("max_hp",1)},default=chance))
        if (rng or random.Random()).uniform(0,100)>max(0,min(100,chance)):
            text=_text(rule,"flee_fail",f"{pid} не удалось сбежать.",player=pid); s["log"].append({"at":_now(),"text":text}); s["turn"]=other; return _put(s)
        return _finish(s,winner=other,loser=pid,reason="flee",rng=rng)
    else: raise ValueError("Неподдерживаемое действие PVP.")
    s["log"].append({"at":_now(),"text":text}); s["turn"]=other; s["round"]=int(s.get("round") or 1)+1
    return _put(s)

def handle_timeout(session_id: str) -> dict[str,Any]:
    """Applies authored AFK action; scheduler/both bot transports may call it."""
    s=get_session(session_id)
    if not s or s.get("state")!="active": raise ValueError("PVP-бой не активен.")
    pid=str(s.get("turn") or ""); row=s["participants"][pid]; row["skips"]=int(row.get("skips") or 0)+1
    rule=s.get("rule") or {}; maximum=max(0,int(rule.get("max_skips") or 0))
    if maximum and row["skips"]>=maximum and rule.get("afk_technical_defeat",True):
        other=s["opponent"] if pid==s["challenger"] else s["challenger"]; return _finish(s,winner=other,loser=pid,reason="afk",rng=random.Random())
    action=str(rule.get("afk_default_action") or s.get("on_timeout") or "skip")
    if action in {"defend","auto"}: return act(session_id,pid,"defend" if action=="defend" else "attack")
    other=s["opponent"] if pid==s["challenger"] else s["challenger"]; s["log"].append({"at":_now(),"text":_text(rule,"afk",f"{pid} пропускает ход из-за AFK.",player=pid)});s["turn"]=other;s["round"]=int(s.get("round") or 1)+1;return _put(s)

def _finish(s: dict[str,Any], *, winner: str, loser: str, reason: str, rng: random.Random|None=None) -> dict[str,Any]:
    s.update({"state":"finished","winner":winner,"loser":loser,"finish_reason":reason,"finished_at":_now()})
    rule=s.get("rule") or {}; curse=None
    achievement_ok=not rule.get("curse_requires_achievement") or str(rule.get("curse_achievement_id") or "") in set((s.get("participants") or {}).get(loser,{}).get("achievements") or [])
    if reason=="death" and achievement_ok and rule.get("postdeath_curse_enabled") and (rule.get("postdeath_curses") or []):
        r=rng or random.Random()
        if r.random()*100 < float(rule.get("postdeath_curse_chance") or 0): curse=r.choice(rule["postdeath_curses"])
    s["postdeath_curse"]={"effect_id":curse,"source":"pvp_player_death","victim":loser,"killer":winner,"duration_seconds":int(rule.get("curse_duration") or 0)} if curse else None
    s["log"].append({"at":_now(),"text":_text(rule,"victory",f"{winner} побеждает {loser}.",winner=winner,loser=loser,reason=reason)})
    return _put(s)

def apply_result_to_players(storage: Any, session_id: str) -> dict[str,Any]:
    s=get_session(session_id)
    if not s or s.get("state")!="finished": raise ValueError("PVP-бой не завершён.")
    if s.get("result_applied"): return s
    get=getattr(storage,"get_player_by_game_id"); update=getattr(storage,"update_player")
    winner=get(s["winner"]); loser=get(s["loser"])
    if not isinstance(winner,dict) or not isinstance(loser,dict): raise ValueError("Игрок результата PVP не найден.")
    winner["pvp_wins"]=int(winner.get("pvp_wins") or 0)+1; loser["pvp_losses"]=int(loser.get("pvp_losses") or 0)+1
    rule=s.get("rule") or {}
    def apply_rows(target: dict[str,Any], rows: list[dict[str,Any]], *, subtract: bool=False, other: dict[str,Any]|None=None) -> None:
        r=random.Random(str(s.get("id"))+str(target.get("game_id")))
        for row in rows:
            if not isinstance(row,dict) or r.uniform(0,100)>float(row.get("chance") or 100):continue
            kind=str(row.get("type") or "");oid=str(row.get("object_id") or row.get("value") or "")
            try:amount=max(0,int(row.get("amount") or (row.get("value") if str(row.get("value") or "").isdigit() else 0) or 0))
            except (TypeError,ValueError):amount=0
            sign=-1 if subtract else 1
            if kind in {"coins","criminal_reward"}: target["money"]=max(0,int(target.get("money") or 0)+sign*amount)
            elif kind=="pvp_points": target["pvp_points"]=max(0,int(target.get("pvp_points") or 0)+sign*amount)
            elif kind in {"reputation","hidden_reputation"} and oid:
                bucket=target.setdefault("hidden_reputations" if kind=="hidden_reputation" else "reputations",{});bucket[oid]=int(bucket.get(oid) or 0)+sign*amount
            elif kind=="experience":
                if subtract:
                    from services.progression_service import apply_death_experience_penalty
                    apply_death_experience_penalty(target,int(row.get("percent") or amount))
                else:
                    from services.progression_service import grant_experience
                    grant_experience(target,amount,source_type="pvp")
            elif kind in {"item","trophy","proof_bag"} and oid:
                if subtract:
                    remaining=max(1,amount)
                    for item in target.get("inventory") or []:
                        if remaining<=0:break
                        if isinstance(item,dict) and str(item.get("item_id") or item.get("id") or "")==oid:
                            take=min(remaining,int(item.get("quantity") or item.get("count") or 1));item["quantity"]=max(0,int(item.get("quantity") or item.get("count") or 1)-take);remaining-=take
                    target["inventory"]=[item for item in target.get("inventory") or [] if not isinstance(item,dict) or int(item.get("quantity") or item.get("count") or 0)>0]
                else:
                    from services.item_registry import build_inventory_item
                    from services.inventory_service import add_inventory_item
                    add_inventory_item(target,build_inventory_item(oid,max(1,amount),item_id=oid),max(1,amount),item_id=oid,default_source="PVP")
            elif kind=="fine":
                from services.fine_service import create_raid_fine
                create_raid_fine(target,oid or "pvp")
            elif kind in {"effect","curse"} and oid:
                target.setdefault("active_effects",[]).append({"effect_id":oid,"source":"pvp_result"})
            elif kind in {"camp","fortress"} and oid: target["location"]=oid
            elif kind=="quest_fail" and oid: target.setdefault("quests",{}).setdefault(oid,{})["status"]="failed"
            elif kind=="quest_progress" and oid:
                from services.quest_runtime_service import progress
                progress(target,"pvp",oid,max(1,amount))
    apply_rows(winner,list(rule.get("victory_rewards") or rule.get("rewards") or []),other=loser)
    loss_rows=list(rule.get("surrender_consequences") or []) if s.get("finish_reason")=="surrender" else list(rule.get("defeat_consequences") or rule.get("penalties") or [])
    apply_rows(loser,loss_rows,subtract=True,other=winner)
    if rule.get("criminal"):
        if rule.get("fine_id"):
            from services.fine_service import create_raid_fine
            create_raid_fine(winner,str(rule["fine_id"]))
        for key,amount_key in (("criminal_reputation_id","criminal_reputation_amount"),("city_reputation_id","city_reputation_amount")):
            if rule.get(key):winner.setdefault("reputations",{})[str(rule[key])]=int(winner.setdefault("reputations",{}).get(str(rule[key])) or 0)+int(rule.get(amount_key) or 0)
        if rule.get("move_to_fortress_id") and random.Random(str(s.get("id"))).uniform(0,100)<=float(rule.get("raid_chance") or 0):winner["location"]=str(rule["move_to_fortress_id"])
        if rule.get("city_ban_id"):winner.setdefault("city_bans",{})[str(rule["city_ban_id"])]=True
        if rule.get("ban_start_locations"):winner["start_locations_banned"]=True
    if rule.get("create_proof_bag") and rule.get("proof_item_id"):
        apply_rows(winner,[{"type":"proof_bag","object_id":rule["proof_item_id"],"amount":1}],other=loser)
    try:
        from services.quest_runtime_service import progress as quest_progress
        quest_progress(winner, "kill_player", str(loser.get("game_id") or ""), 1)
        from services.achievement_engine import record_game_event
        record_game_event(winner, "finish_pvp", 1, str(s.get("rule_id") or ""), storage=storage)
        record_game_event(winner, "win_battle", 1, "pvp", storage=storage)
        record_game_event(loser, "finish_pvp", 1, str(s.get("rule_id") or ""), storage=storage)
        record_game_event(loser, "lose_battle", 1, "pvp", storage=storage)
        if s.get("finish_reason") == "death":
            from services.reputation_runtime_service import apply_trigger
            apply_trigger(winner, "pvp_kill", str(loser.get("game_id") or ""))
    except Exception:
        pass
    if s.get("finish_reason")=="death":
        loser["pvp_deaths"]=int(loser.get("pvp_deaths") or 0)+1
        try:
            from services.achievement_engine import record_game_event
            record_game_event(loser, "death", 1, "pvp", storage=storage)
        except Exception: pass
    curse=s.get("postdeath_curse")
    if curse:
        effects=loser.get("active_effects"); effects=effects if isinstance(effects,list) else []; effects.append(curse); loser["active_effects"]=effects
        loser["pvp_postdeath_curses_received"]=int(loser.get("pvp_postdeath_curses_received") or 0)+1
        try:
            from services.achievement_engine import record_game_event
            record_game_event(loser, "gain_curse", 1, str(curse.get("effect_id") or ""), storage=storage)
        except Exception: pass
    try:
        from services.bot_message_queue import release_waiting
        release_waiting(str(winner.get("game_id") or ""),"battle");release_waiting(str(loser.get("game_id") or ""),"battle")
    except Exception:pass
    update(winner); update(loser); s["result_applied"]=True; return _put(s)
