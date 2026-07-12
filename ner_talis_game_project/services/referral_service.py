"""Реферальные ссылки (чат-ТЗ «передача предметов, реферальные ссылки, …»).

Каждый игрок имеет стабильный реферальный код (его game_id). Ссылка-приглашение
ведёт в бота с deep-link payload `ref_<код>`. При регистрации нового игрока по
такой ссылке он привязывается к рефереру (идемпотентно, не самому себе), а у
реферера растёт счётчик приглашённых.

Слой данных без рантайм-побочек кроме обновления реферера через storage —
основная логика чистая и тестируемая.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

REF_PREFIX = "ref_"
_CODE_RE = re.compile(r"[^A-Za-z0-9_-]")


def referral_code_for(player: dict[str, Any] | None) -> str:
    """Стабильный реферальный код игрока (его уникальный game_id)."""
    return str((player or {}).get("game_id") or (player or {}).get("id") or "").strip()


def parse_referral_code(payload: Any) -> str:
    """Извлечь код из payload /start: «ref_<код>» или просто «<код>»."""
    text = str(payload or "").strip()
    if text.startswith(REF_PREFIX):
        text = text[len(REF_PREFIX):]
    return _CODE_RE.sub("", text)


def telegram_start_payload(player: dict[str, Any] | None) -> str:
    return f"{REF_PREFIX}{referral_code_for(player)}"


def build_telegram_link(player: dict[str, Any] | None) -> str:
    """Deep-link приглашение в Telegram. Пусто, если не задан username бота."""
    bot = os.getenv("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
    code = referral_code_for(player)
    if not bot or not code:
        return ""
    default = f"https://t.me/{bot}?start={REF_PREFIX}{code}"
    try:
        from services.referral_constructor_service import active_rules
        template = next((str(r.get("telegram_link_template") or "") for r in active_rules("telegram") if r.get("telegram_link_template")), "")
        return template.format(bot=bot, code=code, payload=f"{REF_PREFIX}{code}") if template else default
    except (KeyError, ValueError):
        return default


def build_vk_link(player: dict[str, Any] | None) -> str:
    """Ссылка-приглашение в VK-бота с ref-кодом (ТЗ 2.0 файл 16 §3/§6).

    Использует VK_BOT_SCREEN_NAME (например «nertalis») либо club<VK_GROUP_ID>.
    Пусто, если ни то, ни другое не задано.
    """
    screen = os.getenv("VK_BOT_SCREEN_NAME", "").strip().lstrip("@")
    if not screen:
        group_id = os.getenv("VK_GROUP_ID", "").strip()
        screen = f"club{group_id}" if group_id else ""
    code = referral_code_for(player)
    if not screen or not code:
        return ""
    default = f"https://vk.me/{screen}?ref={REF_PREFIX}{code}"
    try:
        from services.referral_constructor_service import active_rules
        template = next((str(r.get("vk_link_template") or "") for r in active_rules("vk") if r.get("vk_link_template")), "")
        return template.format(screen=screen, code=code, payload=f"{REF_PREFIX}{code}") if template else default
    except (KeyError, ValueError):
        return default


_CURRENCY_RATE = {"copper": 1, "silver": 1_000, "gold": 1_000_000,
                  "magic_gold": 1_000_000_000, "ancient_coin": 500_000_000_000}


def _apply_rule_rewards(player: dict[str, Any], rewards: list[dict[str, Any]], claim_key: str) -> bool:
    """Применить безопасное подмножество наград правила ровно один раз."""
    claims = player.get("referral_reward_claims")
    claims = claims if isinstance(claims, list) else []
    if claim_key in claims:
        return False
    changed = False
    for reward in rewards or []:
        if not isinstance(reward, dict):
            continue
        kind = str(reward.get("type") or "")
        try:
            amount = max(1, int(reward.get("amount") or 1))
        except (TypeError, ValueError):
            continue
        object_id = str(reward.get("object_id") or reward.get("currency") or "")
        if kind == "currency":
            player["money"] = int(player.get("money") or 0) + amount * _CURRENCY_RATE.get(object_id or "copper", 1)
            changed = True
        elif kind == "exp":
            player["experience"] = int(player.get("experience") or 0) + amount
            player["total_experience"] = int(player.get("total_experience") or 0) + amount
            changed = True
        elif kind == "item" and object_id:
            try:
                from services.inventory_service import add_inventory_item
                from services.item_registry import build_inventory_item
                add_inventory_item(player, build_inventory_item(object_id, amount, item_id=object_id), amount, default_source="referral")
                changed = True
            except Exception:
                continue
        elif kind == "energy":
            player["energy"] = int(player.get("energy") or 0) + amount; changed = True
        elif kind in ("skill_points", "stat_points"):
            key = "free_skill_points" if kind == "skill_points" else "free_stat_points"
            player[key] = int(player.get(key) or 0) + amount; changed = True
        elif kind in ("effect", "achievement", "reputation") and object_id:
            try:
                if kind == "effect":
                    from services.effect_formula_runtime import apply_to_player
                    apply_to_player(player, object_id, source="referral", context={"duration_seconds": reward.get("duration_seconds")})
                elif kind == "achievement":
                    from services.achievement_engine import grant
                    grant(None, player, object_id, source="referral", save=False, notify=False)
                else:
                    from services.reputation_runtime_service import change
                    change(player, object_id, amount, source="referral")
                changed = True
            except Exception: continue
        elif kind in ("title", "promo", "access", "special") and object_id:
            bucket = {"title":"titles", "promo":"received_promocodes", "access":"referral_accesses", "special":"special_rewards"}[kind]
            values = player.setdefault(bucket, [])
            if object_id not in values: values.append(object_id)
            changed = True
    claims.append(claim_key)
    player["referral_reward_claims"] = claims[-500:]
    return changed

def _history(player: dict[str, Any]) -> list[dict[str, Any]]:
    rows = player.setdefault("referral_history", [])
    return rows if isinstance(rows, list) else []

def _condition_met(rule: dict[str, Any], player: dict[str, Any], event: str, value: Any = None) -> bool:
    trigger = str(rule.get("trigger") or "registration_complete")
    if trigger != event: return False
    target = int(rule.get("trigger_value") or 0)
    if trigger == "level_reached": return int(value if value is not None else player.get("level") or 1) >= max(1, target)
    if trigger == "play_minutes": return int(value if value is not None else player.get("play_minutes") or 0) >= max(1, target)
    if trigger == "activity_reached": return int(value if value is not None else player.get("activity_points") or 0) >= max(1, target)
    if trigger == "starter_quest" and rule.get("trigger_object_id"): return str(value or "") == str(rule["trigger_object_id"])
    return True

def _rule_allowed(rule: dict[str, Any], referrer: dict[str, Any], player: dict[str, Any]) -> tuple[bool, str]:
    gid, rid = referral_code_for(player), referral_code_for(referrer)
    if gid == rid: return False, "self_referral"
    if gid in {str(x) for x in rule.get("excluded_nt_ids") or []}: return False, "excluded"
    rows = _history(referrer); successes = [x for x in rows if x.get("status") == "credited" and x.get("rule_id") == rule.get("id")]
    now = datetime.now(timezone.utc); today = now.date(); week = now.isocalendar()[:2]
    parse = lambda x: datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    daily = [x for x in successes if x.get("at") and parse(x["at"]).date() == today]
    weekly = [x for x in successes if x.get("at") and parse(x["at"]).isocalendar()[:2] == week]
    for key, count in (("total_limit", len(successes)), ("per_referrer_limit", len(successes)), ("daily_limit", len(daily)), ("daily_reward_limit", len(daily)), ("weekly_limit", len(weekly)), ("weekly_reward_limit", len(weekly))):
        if int(rule.get(key) or 0) and count >= int(rule[key]): return False, key
    fingerprint = str(player.get("registration_device") or ""); ip = str(player.get("registration_ip") or "")
    if fingerprint and int(rule.get("device_limit") or 0) and sum(x.get("device") == fingerprint for x in rows) >= int(rule["device_limit"]): return False, "device_limit"
    if ip and int(rule.get("ip_limit") or 0) and sum(x.get("ip") == ip for x in rows) >= int(rule["ip_limit"]): return False, "ip_limit"
    return True, ""

def process_referral_event(storage: Any, player: dict[str, Any], event: str, value: Any = None) -> bool:
    """Засчитать привязанного реферала при выполнении authored-условия."""
    code = str(player.get("referred_by") or ""); gid = referral_code_for(player)
    if not code or not gid: return False
    referrer = storage.get_player_by_game_id(code)
    if not isinstance(referrer, dict): return False
    from services.referral_constructor_service import active_rules
    rules = active_rules(str(player.get("main_platform") or "all")); changed = False
    for rule in rules:
        if not _condition_met(rule, player, event, value): continue
        rule_id = str(rule.get("id") or "rule"); invite_id = f"{rule_id}:{code}:{gid}"
        if any(x.get("invite_id") == invite_id and x.get("status") in ("credited", "pending_review") for x in _history(referrer)): continue
        allowed, reason = _rule_allowed(rule, referrer, player)
        status = "pending_review" if allowed and rule.get("manual_review") else ("credited" if allowed else "rejected")
        row = {"invite_id":invite_id,"rule_id":rule_id,"campaign_id":rule.get("campaign_id"),"referrer_nt_id":code,"referred_nt_id":gid,"platform":player.get("main_platform"),"event":event,"status":status,"reason":reason,"at":datetime.now(timezone.utc).isoformat(),"device":player.get("registration_device"),"ip":player.get("registration_ip")}
        _history(referrer).append(dict(row)); _history(player).append(dict(row))
        if status != "credited": continue
        refs = referrer.setdefault("referrals", [])
        if gid not in refs: refs.append(gid); referrer["referral_count"] = len(refs)
        changed |= _apply_rule_rewards(referrer, rule.get("referrer_rewards") or [], f"{invite_id}:referrer")
        changed |= _apply_rule_rewards(player, rule.get("referred_rewards") or [], f"{invite_id}:referred")
    storage.update_player(referrer); storage.update_player(player)
    return changed or any(x.get("referred_nt_id") == gid for x in _history(referrer))

def referral_statistics(storage: Any) -> dict[str, Any]:
    rows=[]
    for brief in (storage.list_player_audience_rows() if hasattr(storage,"list_player_audience_rows") else []):
        player=storage.get_player_by_game_id(str(brief.get("game_id") or "")) or {}
        rows.extend(x for x in _history(player) if x.get("referrer_nt_id")==player.get("game_id"))
    unique={str(x.get("invite_id")):x for x in rows}
    values=list(unique.values())
    return {"total":len(values),"credited":sum(x.get("status")=="credited" for x in values),"pending":sum(x.get("status")=="pending_review" for x in values),"rejected":sum(x.get("status")=="rejected" for x in values),"history":sorted(values,key=lambda x:str(x.get("at") or ""),reverse=True)[:1000]}

def review_invitation(storage: Any, invite_id: str, approve: bool, reason: str = "") -> bool:
    stats=referral_statistics(storage); row=next((x for x in stats["history"] if x.get("invite_id")==invite_id and x.get("status")=="pending_review"),None)
    if not row:return False
    referrer=storage.get_player_by_game_id(str(row.get("referrer_nt_id") or ""));player=storage.get_player_by_game_id(str(row.get("referred_nt_id") or ""))
    if not isinstance(referrer,dict) or not isinstance(player,dict):return False
    env=__import__("services.referral_constructor_service",fromlist=["store"]).store().get(str(row.get("rule_id") or ""));rule={"id":row.get("rule_id"),**((env or {}).get("data") or {})}
    status="credited" if approve else "rejected"
    for owner in (referrer,player):
        for saved in _history(owner):
            if saved.get("invite_id")==invite_id:saved["status"]=status;saved["review_reason"]=reason;saved["reviewed_at"]=datetime.now(timezone.utc).isoformat()
    if approve:
        gid=referral_code_for(player);refs=referrer.setdefault("referrals",[])
        if gid not in refs:refs.append(gid);referrer["referral_count"]=len(refs)
        _apply_rule_rewards(referrer,rule.get("referrer_rewards") or [],f"{invite_id}:referrer")
        _apply_rule_rewards(player,rule.get("referred_rewards") or [],f"{invite_id}:referred")
    storage.update_player(referrer);storage.update_player(player);return True


def apply_registration_referral_rules(storage: Any, referrer: dict[str, Any], new_player: dict[str, Any]) -> bool:
    try:
        from services.referral_constructor_service import active_rules
        platform = str(new_player.get("main_platform") or "all")
        rules = active_rules(platform)
    except Exception:
        return False
    return process_referral_event(storage, new_player, "registration_complete")


def mark_referred_by(new_player: dict[str, Any], code: Any) -> str | None:
    """Пометить новичка как приглашённого (локально, ДО save_new_player).

    Только ставит ``referred_by`` на самого новичка — без побочек на реферера.
    Возвращает нормализованный код реферера или None, если привязки нет."""
    code = parse_referral_code(code)
    if not code or not isinstance(new_player, dict):
        return None
    new_id = referral_code_for(new_player)
    if not new_id or code == new_id:
        return None
    if new_player.get("referred_by"):
        return None
    new_player["referred_by"] = code
    return code


def credit_referrer(storage: Any, new_player: dict[str, Any]) -> bool:
    """Начислить рефереру приглашённого — вызывать ТОЛЬКО ПОСЛЕ успешного
    создания новичка (15-CODEX §6). Идемпотентно: повторный вызов или повторное
    подтверждение регистрации не создаёт дубль и не увеличивает счётчик дважды
    (счётчик завязан на добавление в список referrals — единый источник истины)."""
    if not isinstance(new_player, dict):
        return False
    code = str(new_player.get("referred_by") or "").strip()
    new_id = referral_code_for(new_player)
    if not code or not new_id or code == new_id:
        return False
    get_player = getattr(storage, "get_player_by_game_id", None)
    referrer = get_player(code) if callable(get_player) else None
    if not isinstance(referrer, dict):
        return False
    if any(x.get("referred_nt_id") == new_id for x in _history(referrer)) or new_id in (referrer.get("referrals") or []):
        return False  # уже учтён — идемпотентно, без повторного инкремента
    try:
        from services.referral_constructor_service import active_rules
        has_rules = bool(active_rules(str(new_player.get("main_platform") or "all")))
    except Exception: has_rules = False
    if has_rules:
        apply_registration_referral_rules(storage, referrer, new_player)
    else:
        refs = referrer.setdefault("referrals", []); refs.append(new_id); referrer["referral_count"] = len(refs)
        row={"invite_id":f"legacy:{code}:{new_id}","rule_id":"legacy","referrer_nt_id":code,"referred_nt_id":new_id,"event":"registration_complete","status":"credited","at":datetime.now(timezone.utc).isoformat()}
        _history(referrer).append(dict(row));_history(new_player).append(dict(row))
    update_player = getattr(storage, "update_player", None)
    if callable(update_player):
        try:
            update_player(referrer)
        except Exception:
            pass
        try:
            update_player(new_player)
        except Exception:
            pass
    return True


def attach_referral(storage: Any, new_player: dict[str, Any], code: Any) -> bool:
    """Совместимость: пометить новичка и сразу начислить рефереру.

    ВАЖНО (15-CODEX §6): начисление здесь происходит немедленно, поэтому в потоке
    регистрации используйте раздельно mark_referred_by (до save_new_player) и
    credit_referrer (после успешного сохранения), чтобы при сбое создания игрока
    реферер не получил фиктивного приглашённого."""
    if mark_referred_by(new_player, code) is None:
        return False
    return credit_referrer(storage, new_player)


def referral_summary(player: dict[str, Any] | None) -> dict[str, Any]:
    """Данные для профиля: код, ссылка, число приглашённых, кем приглашён."""
    player = player or {}
    return {
        "code": referral_code_for(player),
        "link": build_telegram_link(player),
        "vkLink": build_vk_link(player),
        "count": int(player.get("referral_count") or 0),
        "referredBy": str(player.get("referred_by") or ""),
    }
