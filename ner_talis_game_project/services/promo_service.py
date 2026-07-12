"""Сервис промокодов Нер-Талис."""

from __future__ import annotations

import json
import os
import random
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from project_paths import resolve_project_path
from services.derived_stats_service import calculate_energy_stats
from services.inventory_service import add_inventory_item, recalculate_inventory_overflow
from services.item_registry import get_item_definition_by_id, registry_item_to_inventory_item, slugify_fallback_item_id
from services.progression_service import grant_experience

try:  # POSIX file lock for JSON fallback storage.
    import fcntl  # type: ignore
except Exception:  # pragma: no cover - Windows fallback keeps thread safety via storage locks only.
    fcntl = None  # type: ignore


def _promo_path() -> Path:
    return resolve_project_path(os.getenv("PROMO_CODES_PATH", "data/promo_codes.json"))


def _normalize_code(code: str) -> str:
    """Canonical promo key: no leading slash(es), trimmed, upper-cased.

    Admins may enter "/START100" while a player redeems "/promo start100";
    both must resolve to the same code. The canonical form has no slash.
    """
    return str(code or "").strip().lstrip("/").strip().upper()

def promo_from_command(storage:Any,text:str,platform:str="")->tuple[str,str]|None:
    parts=str(text or "").strip().split(maxsplit=1);command=(parts[0] if parts else "").casefold();argument=parts[1].strip() if len(parts)>1 else ""
    for promo in (load_promo_data(storage).get("codes") or {}).values():
        configured=str(promo.get("command") or "/promo").strip().casefold()
        if not configured.startswith("/"):configured="/"+configured
        allowed=str(promo.get("platform") or "both")
        if command==configured and allowed in {"","all","both",platform} and promo.get("command_active",True):
            expected=str(promo.get("code_after_command") or promo.get("code") or "").strip()
            if configured=="/promo":return promo.get("code"),argument
            return promo.get("code"),argument or expected
    return None


def _parse_promo_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@contextmanager
def _file_locked() -> Iterator[None]:
    path = _promo_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _storage_supports_promo(storage: Any | None) -> bool:
    return storage is not None and hasattr(storage, "load_promo_data") and hasattr(storage, "save_promo_data")


def load_promo_data(storage: Any | None = None) -> dict[str, Any]:
    if _storage_supports_promo(storage):
        data = storage.load_promo_data()
        if isinstance(data, dict):
            data.setdefault("codes", {})
            return data
    path = _promo_path()
    if not path.exists():
        return {"codes": {}}
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError:
        return {"codes": {}}
    if not isinstance(data, dict):
        return {"codes": {}}
    data.setdefault("codes", {})
    return data


def save_promo_data(data: dict[str, Any], storage: Any | None = None) -> None:
    if _storage_supports_promo(storage):
        storage.save_promo_data(data)
        return
    path = _promo_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2, default=str)


def add_promo_code(*, code: str, uses_left: int, reward: dict[str, Any], expires_at: str | None = None, one_use_per_player: bool = True, note: str = "", storage: Any | None = None, config:dict[str,Any]|None=None) -> dict[str, Any]:
    normalized_code = _normalize_code(code)
    if not normalized_code:
        raise ValueError("Код промокода пустой.")
    if not isinstance(reward, dict):
        raise ValueError("Награда промокода должна быть JSON-объектом.")
    uses = int(uses_left)
    if uses <= 0:
        raise ValueError("Количество использований должно быть больше 0.")

    promo = {
        "code": normalized_code,
        "active": True,
        "uses_left": uses,
        "reward": reward,
        "expires_at": expires_at,
        "one_use_per_player": bool(one_use_per_player),
        "used_by": [],
        "note": note,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "activation_history": [],
        **{k:v for k,v in (config or {}).items() if k not in {"code","reward","used_by","activation_history","created_at","updated_at"}},
    }
    # Single-row upsert avoids the "DELETE all + reinsert all" rewrite that could
    # drop a concurrently created code.
    if storage is not None and callable(getattr(storage, "save_promo_code", None)):
        storage.save_promo_code(normalized_code, promo)
        return promo
    with _file_locked() if storage is None else _null_context():
        data = load_promo_data(storage)
        data["codes"][normalized_code] = promo
        save_promo_data(data, storage)
        return promo


@contextmanager
def _null_context() -> Iterator[None]:
    yield


def import_promo_codes(items: list[dict[str, Any]], storage: Any | None = None) -> int:
    imported = 0
    for item in items:
        add_promo_code(
            code=str(item.get("code", "")),
            uses_left=int(item.get("uses_left", item.get("uses", 1))),
            reward=item.get("reward") or {},
            expires_at=item.get("expires_at"),
            one_use_per_player=bool(item.get("one_use_per_player", True)),
            note=str(item.get("note", "")),
            storage=storage,
        )
        imported += 1
    return imported


def deactivate_promo_code(code: str, storage: Any | None = None) -> bool:
    normalized_code = _normalize_code(code)
    if storage is not None and callable(getattr(storage, "save_promo_code", None)):
        promo = (load_promo_data(storage).get("codes") or {}).get(normalized_code)
        if not promo:
            return False
        promo["active"] = False
        promo["updated_at"] = datetime.now(timezone.utc).isoformat()
        storage.save_promo_code(normalized_code, promo)
        return True
    with _file_locked() if storage is None else _null_context():
        data = load_promo_data(storage)
        promo = data.get("codes", {}).get(normalized_code)
        if not promo:
            return False
        promo["active"] = False
        promo["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_promo_data(data, storage)
        return True


def _matching_stored_keys(data: dict[str, Any], normalized_code: str) -> list[str]:
    """Stored keys whose canonical form equals ``normalized_code``.

    Legacy promos created before slash-stripping were saved with a leading
    slash (e.g. ``/PROMO_CODE 111``). Matching on the canonical form lets the
    admin panel delete them regardless of how they were originally stored.
    """
    codes = data.get("codes") or {}
    return [key for key in codes if _normalize_code(key) == normalized_code]


def delete_promo_code(code: str, storage: Any | None = None) -> bool:
    normalized_code = _normalize_code(code)
    if storage is not None and callable(getattr(storage, "delete_promo_code", None)):
        targets = _matching_stored_keys(load_promo_data(storage), normalized_code)
        if normalized_code not in targets:
            targets.append(normalized_code)
        # Удаляем ВСЕ совпавшие ключи (legacy «/PROMO» и нормализованный «PROMO»
        # одновременно). any(...) останавливался после первого успешного удаления
        # и оставлял дубликат активным/видимым.
        deleted = False
        for key in targets:
            if storage.delete_promo_code(key):
                deleted = True
        return deleted
    with _file_locked() if storage is None else _null_context():
        data = load_promo_data(storage)
        targets = _matching_stored_keys(data, normalized_code)
        if not targets:
            return False
        for key in targets:
            data["codes"].pop(key, None)
        save_promo_data(data, storage)
        return True


def list_promo_codes(limit: int = 20, storage: Any | None = None) -> list[dict[str, Any]]:
    data = load_promo_data(storage)
    promos = list(data.get("codes", {}).values())
    promos.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return promos[:max(1, limit)]


def _promo_reward_inventory_item(item: dict[str, Any], amount: int) -> dict[str, Any]:
    """Build a real inventory item for a promo reward.

    Admin/promo JSON usually stores only {"item_id": "...", "amount": N}.
    Without registry enrichment such rewards turn into bare technical stacks with
    no Russian name, icon, stack size, sell price or use effect.  Start from the
    canonical item registry, then let explicit promo JSON fields override it so
    special event rewards can still customize the item.
    """

    item_id = str(item.get("item_id") or item.get("id") or "").strip()
    item_name = str(item.get("name") or item.get("name_ru") or item_id or "promo_item").strip()

    explicit_source = item.get("source") is not None
    definition = get_item_definition_by_id(item_id) if item_id else None
    if definition is not None:
        prepared = registry_item_to_inventory_item(definition, amount)
    else:
        # Do not fall back from a mistyped item_id to a registry lookup by name:
        # that would attach another item's stats/effects/icons to an unknown id.
        fallback_id = item_id or slugify_fallback_item_id(item_name or "promo_item")
        prepared = {
            "id": fallback_id,
            "item_id": fallback_id,
            "name": item_name or fallback_id,
            "name_ru": item_name or fallback_id,
            "category": "Ресурсы",
            "type": "Материал",
            "quality": "обычный",
            "amount": amount,
            "max_stack": 999,
            "stackable": True,
            "source": "promo_code",
            "actions": [],
        }

    for key, value in item.items():
        if key == "amount" or value is None:
            continue
        prepared[key] = value

    if item_id:
        prepared["id"] = item_id
        prepared["item_id"] = item_id
    prepared["amount"] = amount
    if not explicit_source:
        prepared["source"] = "promo_code"
    return prepared


def apply_reward_to_player(player: dict[str, Any], reward: dict[str, Any]) -> dict[str, Any]:
    money_reward = int(reward.get("money_copper", reward.get("money", 0)) or 0)
    if money_reward:
        try:
            from services.economy_runtime import change,reward_amount
            money_reward=reward_amount("promo",money_reward,{"player_level":player.get("level",1)});change(player,"copper",money_reward,operation="promo_reward",source="promo")
        except (ImportError,ValueError,OSError):
            current_money = int(player.get("money_copper", player.get("money", 0)) or 0)
            new_money = max(0, current_money + money_reward)
            player["money_copper"] = new_money
            player["money"] = new_money

    energy_reward = int(reward.get("current_energy", reward.get("energy", 0)) or 0)
    if energy_reward:
        energy_stats = calculate_energy_stats(player)
        max_energy = int(energy_stats["max_energy"])
        current_energy = int(energy_stats["current_energy"])
        new_energy = min(max_energy, max(0, current_energy + energy_reward))
        player["current_energy"] = new_energy
        player["energy"] = new_energy

    if "free_stat_points" in reward:
        player["free_stat_points"] = int(player.get("free_stat_points", 0)) + int(reward.get("free_stat_points") or 0)
    if "free_skill_points" in reward:
        player["free_skill_points"] = int(player.get("free_skill_points", 0)) + int(reward.get("free_skill_points") or 0)

    experience_reward = int(reward.get("experience", reward.get("exp", reward.get("xp", 0))) or 0)
    if experience_reward > 0:
        grant_experience(player, experience_reward)

    for item in reward.get("items") or []:
        if isinstance(item, dict):
            amount = int(item.get("amount", 1) or 0)
            if amount <= 0:
                continue
            prepared_item = _promo_reward_inventory_item(item, amount)
            add_inventory_item(player, prepared_item, amount, default_source="promo_code")
    for row in reward.get("rewards") or []:
        if not isinstance(row,dict):continue
        kind=str(row.get("type") or "");oid=str(row.get("object_id") or row.get("item_id") or row.get("effect_id") or "");minimum=max(1,int(row.get("min_amount") or row.get("amount") or 1));maximum=max(minimum,int(row.get("max_amount") or minimum));amount=random.randint(minimum,maximum)
        if kind=="item" and oid:
            prepared=_promo_reward_inventory_item({**row,"item_id":oid},amount);mode=str(row.get("delivery_mode") or "inventory")
            if row.get("bind_on_receive"):prepared["bound_on_receive"]=True
            if mode=="delivery":player.setdefault("promo_delivery_inbox",[]).append({"item":prepared,"amount":amount,"text":row.get("text")})
            else:
                if mode=="reject":
                    from copy import deepcopy
                    simulated=deepcopy(player);preview=add_inventory_item(simulated,prepared,amount,default_source="promo_code")
                    if preview.added<amount:raise ValueError("Инвентарь заполнен, награду промокода получить нельзя.")
                add_inventory_item(player,prepared,amount,default_source="promo_code")
        elif kind in {"currency","coins"}:
            from services.economy_runtime import change,reward_amount
            change(player,str(row.get("currency") or oid or "copper"),reward_amount("promo",amount),operation="promo_reward",source="promo")
        elif kind in {"experience","exp"}:grant_experience(player,amount)
        elif kind=="energy":
            stats=calculate_energy_stats(player);player["energy"]=player["current_energy"]=min(int(stats["max_energy"]),int(stats["current_energy"])+amount)
        elif kind in {"skill_points","stat_points"}:player["free_skill_points" if kind=="skill_points" else "free_stat_points"]=int(player.get("free_skill_points" if kind=="skill_points" else "free_stat_points") or 0)+amount
        elif kind in {"effect","curse"}:
            from services.effect_formula_runtime import apply_to_player
            apply_to_player(player,oid,source="promo",context={"duration_seconds":row.get("duration_seconds")})
        elif kind=="achievement":
            from services.achievement_engine import grant
            grant(None,player,oid,source="promo",save=False,notify=False)
        elif kind in {"reputation","hidden_reputation"}:
            bucket=player.setdefault("hidden_reputations" if kind=="hidden_reputation" else "reputations",{});bucket[oid]=int(bucket.get(oid) or 0)+amount
        elif kind in {"access","location","sublocation","npc","recipe","skill"}:player.setdefault("unlocks",{})[oid]=True
        elif kind=="system_flag":player.setdefault("system_flags",{})[oid]=row.get("value",True)
    recalculate_inventory_overflow(player)
    return player

def _promo_condition_error(player:dict[str,Any],promo:dict[str,Any],*,platform:str="") -> str:
    now=datetime.now(timezone.utc);start=_parse_promo_datetime(promo.get("starts_at"))
    if start and now<start:return str(promo.get("not_started_text") or "Промокод ещё не активен.")
    actual_platform=platform or str(player.get("platform") or next(iter((player.get("linked_accounts") or {})),""))
    allowed=str(promo.get("platform") or "both")
    if allowed not in {"","all","both",actual_platform}:return str(promo.get("condition_error_text") or "Промокод недоступен на этой платформе.")
    level=int(player.get("level") or 1)
    if level<int(promo.get("min_level") or 0) or int(promo.get("max_level") or 0) and level>int(promo.get("max_level")):return str(promo.get("condition_error_text") or "Уровень игрока не подходит.")
    if promo.get("required_race") and str(player.get("race_id") or "")!=str(promo["required_race"]):return str(promo.get("condition_error_text") or "Раса игрока не подходит.")
    gid=str(player.get("game_id") or player.get("id") or "");only={str(x) for x in promo.get("allowed_players") or []};excluded={str(x) for x in promo.get("excluded_players") or []}
    if only and gid not in only or gid in excluded:return str(promo.get("condition_error_text") or "Промокод недоступен этому игроку.")
    history=[row for row in promo.get("activation_history") or [] if isinstance(row,dict) and row.get("status")=="success"]
    personal=[row for row in history if str(row.get("game_id"))==gid];now_day=now.date();year,week,_=now.isocalendar()
    if int(promo.get("per_player_limit") or 0) and len(personal)>=int(promo["per_player_limit"]):return str(promo.get("already_used_text") or "Лимит активаций для игрока исчерпан.")
    daily=sum(1 for row in personal if (_parse_promo_datetime(row.get("at")) or datetime.min.replace(tzinfo=timezone.utc)).date()==now_day)
    weekly=sum(1 for row in personal if (_parse_promo_datetime(row.get("at")) or datetime.min.replace(tzinfo=timezone.utc)).isocalendar()[:2]==(year,week))
    if int(promo.get("daily_limit") or 0) and daily>=int(promo["daily_limit"]):return str(promo.get("limit_text") or "Дневной лимит промокода исчерпан.")
    if int(promo.get("weekly_limit") or 0) and weekly>=int(promo["weekly_limit"]):return str(promo.get("limit_text") or "Недельный лимит промокода исчерпан.")
    if promo.get("required_item_id") and not any(str((x or {}).get("item_id") or (x or {}).get("id") or "")==str(promo["required_item_id"]) for x in player.get("inventory") or [] if isinstance(x,dict)):return str(promo.get("condition_error_text") or "Нет требуемого предмета.")
    if promo.get("required_achievement_id"):
        state=player.get("achievements") or {};earned=state.get("earned",{}) if isinstance(state,dict) else state
        if str(promo["required_achievement_id"]) not in earned:return str(promo.get("condition_error_text") or "Нет требуемого достижения.")
    if promo.get("required_quest_id") and str(promo["required_quest_id"]) not in ((player.get("quests") or {}).get("completed") or {}):return str(promo.get("condition_error_text") or "Не выполнен требуемый квест.")
    if promo.get("required_location_id") and str(player.get("location_id") or player.get("current_location") or "")!=str(promo["required_location_id"]):return str(promo.get("condition_error_text") or "Промокод недоступен в этой локации.")
    if promo.get("required_effect_id") and str(promo["required_effect_id"]) not in {str(x.get("effect_id") or x.get("id") or "") for x in [*(player.get("active_effects") or []),*(player.get("active_curses") or [])] if isinstance(x,dict)}:return str(promo.get("condition_error_text") or "Нет требуемого эффекта.")
    created=_parse_promo_datetime(player.get("created_at"));age_days=(now-created).days if created else 9999;threshold=max(1,int(promo.get("new_player_days") or 7))
    if promo.get("new_players_only") and age_days>threshold or promo.get("old_players_only") and age_days<=threshold:return str(promo.get("condition_error_text") or "Возраст персонажа не подходит.")
    platform_count=sum(1 for row in history if str(row.get("platform") or "")==actual_platform)
    if int(promo.get("platform_limit") or 0) and platform_count>=int(promo["platform_limit"]):return str(promo.get("limit_text") or "Лимит активаций платформы исчерпан.")
    if promo.get("requires_no_fine") or promo.get("requires_fine"):
        try:
            from services.fine_service import active_fines
            fined=bool(active_fines(player))
        except Exception:fined=False
        if promo.get("requires_no_fine") and fined or promo.get("requires_fine") and not fined:return str(promo.get("condition_error_text") or "Условия по штрафам не выполнены.")
    for field,bucket_name in (("required_reputation_id","reputations"),("required_hidden_reputation_id","hidden_reputations")):
        rid=str(promo.get(field) or "")
        if rid and float((player.get(bucket_name) or {}).get(rid) or 0)<float(promo.get("required_reputation_value") or 0):return str(promo.get("condition_error_text") or "Недостаточная репутация.")
    return ""

def validate_promo(code:str,uses_left:int,reward:dict[str,Any],config:dict[str,Any]|None=None,storage:Any|None=None)->dict[str,Any]:
    cfg=config or {};errors=[];warnings=[];normalized=_normalize_code(code)
    if not normalized:errors.append("Не заполнен код промокода.")
    if not str(cfg.get("command") or "/promo").strip():errors.append("Не заполнена команда промокода.")
    if int(uses_left)<0:errors.append("Лимит использований не может быть отрицательным.")
    start=_parse_promo_datetime(cfg.get("starts_at"));end=_parse_promo_datetime(cfg.get("expires_at"))
    if start and end and end<=start:errors.append("Дата окончания должна быть позже даты начала.")
    if storage is not None and normalized in (load_promo_data(storage).get("codes") or {}):errors.append("Промокод с таким кодом уже существует.")
    rows=reward.get("rewards") or []
    if not reward:errors.append("Активный промокод должен содержать хотя бы одну награду.")
    for i,row in enumerate(rows,1):
        if not isinstance(row,dict):errors.append(f"Награда #{i}: неверный формат.");continue
        kind=str(row.get("type") or "");oid=str(row.get("object_id") or row.get("item_id") or row.get("effect_id") or "")
        if kind=="item" and not get_item_definition_by_id(oid):errors.append(f"Награда #{i}: предмет «{oid}» не существует или не опубликован.")
        if kind in {"effect","curse"}:
            from services.effect_constructor_service import published_definition
            if not published_definition(oid):errors.append(f"Награда #{i}: эффект «{oid}» не существует или не опубликован.")
            if kind=="curse":warnings.append(f"Награда #{i} выдаёт проклятье.")
    if not end:warnings.append("Промокод не имеет срока окончания.")
    return {"ok":not errors,"errors":errors,"warnings":warnings}

def _record_activation(storage:Any,code:str,player:dict[str,Any],reward:dict[str,Any],status:str="success",error:str="",platform:str="")->None:
    data=load_promo_data(storage);promo=(data.get("codes") or {}).get(_normalize_code(code))
    if not promo:return
    promo.setdefault("activation_history",[]).append({"game_id":str(player.get("game_id") or player.get("id") or ""),"nt_id":str(player.get("game_id") or ""),"platform":platform or player.get("platform"),"at":datetime.now(timezone.utc).isoformat(),"reward":reward,"status":status,"error":error})
    promo["activation_history"]=promo["activation_history"][-5000:];save_promo_data(data,storage)


_CLAIM_FAILURE_MESSAGES = {
    "not_found": "Промокод не найден или отключён.",
    "inactive": "Промокод не найден или отключён.",
    "broken_expiry": "Промокод повреждён: неверный expires_at.",
    "expired": "Срок действия промокода истёк.",
    "already_used": "Этот промокод уже использован этим игроком.",
    "exhausted": "Лимит использований промокода закончился.",
}


def _redeem_with_atomic_claim(storage: Any, game_id: str, code: str,platform:str="") -> tuple[bool, str]:
    """Atomic redemption: storage reserves one use before the reward is granted.

    The storage-level claim (SELECT ... FOR UPDATE / BEGIN IMMEDIATE / lock)
    guarantees two concurrent redemptions cannot exceed ``uses_left`` nor grant a
    second reward to the same player. If the player update then fails, the use is
    refunded so the code is not silently consumed.
    """
    player = storage.get_player_by_game_id(game_id)
    if player is None:
        return False, "Игрок не найден."
    promo=(load_promo_data(storage).get("codes") or {}).get(_normalize_code(code)) or {};condition_error=_promo_condition_error(player,promo,platform=platform)
    if condition_error:_record_activation(storage,code,player,promo.get("reward") or {},"error",condition_error,platform);return False,condition_error

    # Pass the canonical code so the storage claim matches the stored key
    # regardless of case or a leading slash the player/admin may have typed.
    ok, reason, reward = storage.claim_promo_use(_normalize_code(code), str(game_id))
    if not ok:
        message=_CLAIM_FAILURE_MESSAGES.get(reason, "Промокод не найден или отключён.");_record_activation(storage,code,player,promo.get("reward") or {},"error",message,platform);return False,message

    try:
        player = apply_reward_to_player(player, reward or {})
        try:
            from services.achievement_engine import record_game_event
            record_game_event(player, "use_promo", 1, _normalize_code(code), storage=storage)
            from services.reputation_runtime_service import apply_trigger
            apply_trigger(player,"promo",_normalize_code(code),reason="Активация промокода")
            from services.event_campaign_runtime import progress as event_progress
            event_progress(player, "use_promo", _normalize_code(code), 1, storage=storage)
        except Exception:
            pass
        storage.update_player(player)
        _record_activation(storage,code,player,reward or {},platform=platform)
    except Exception:
        try:
            storage.refund_promo_use(_normalize_code(code), str(game_id))
        except Exception:
            pass
        raise
    return True, _promo_text(promo.get("success_text") or "Промокод успешно применён.")


def redeem_promo_code(storage: Any, game_id: str, code: str,*,platform:str="") -> tuple[bool, str]:
    # Preferred path: the storage exposes an atomic claim/refund pair.
    if callable(getattr(storage, "claim_promo_use", None)) and callable(getattr(storage, "refund_promo_use", None)):
        return _redeem_with_atomic_claim(storage, game_id, code,platform)

    # File fallback: guard read-modify-write with a file lock.
    with _file_locked() if not _storage_supports_promo(storage) else _null_context():
        data = load_promo_data(storage)
        normalized_code = _normalize_code(code)
        promo = data.get("codes", {}).get(normalized_code)
        if not promo or not promo.get("active"):
            return False, "Промокод не найден или отключён."

        expires_at = promo.get("expires_at")
        if expires_at:
            parsed_expires_at = _parse_promo_datetime(expires_at)
            if parsed_expires_at is None:
                return False, "Промокод повреждён: неверный expires_at."
            if parsed_expires_at < datetime.now(timezone.utc):
                return False, "Срок действия промокода истёк."

        used_by = {str(value) for value in promo.get("used_by", [])}
        if promo.get("one_use_per_player", True) and str(game_id) in used_by:
            return False, "Этот промокод уже использован этим игроком."

        uses_left = int(promo.get("uses_left", 0))
        if uses_left <= 0:
            return False, "Лимит использований промокода закончился."

        player = storage.get_player_by_game_id(game_id)
        if player is None:
            return False, "Игрок не найден."
        condition_error=_promo_condition_error(player,promo,platform=platform)
        if condition_error:promo.setdefault("activation_history",[]).append({"game_id":str(game_id),"platform":platform,"at":datetime.now(timezone.utc).isoformat(),"status":"error","error":condition_error});save_promo_data(data,storage);return False,condition_error

        player = apply_reward_to_player(player, promo.get("reward") or {})
        try:
            from services.achievement_engine import record_game_event
            record_game_event(player, "use_promo", 1, normalized_code, storage=storage)
            from services.reputation_runtime_service import apply_trigger
            apply_trigger(player,"promo",normalized_code,reason="Активация промокода")
            from services.event_campaign_runtime import progress as event_progress
            event_progress(player, "use_promo", normalized_code, 1, storage=storage)
        except Exception:
            pass
        storage.update_player(player)

        promo.setdefault("used_by", []).append(str(game_id))
        promo["uses_left"] = uses_left - 1
        promo["updated_at"] = datetime.now(timezone.utc).isoformat()
        promo.setdefault("activation_history",[]).append({"game_id":str(game_id),"nt_id":str(game_id),"platform":platform or player.get("platform"),"at":datetime.now(timezone.utc).isoformat(),"reward":promo.get("reward") or {},"status":"success","error":""})
        save_promo_data(data, storage)
        return True, _promo_text(promo.get("success_text") or "Промокод успешно применён.")
def _promo_text(value:Any)->str:
    text=str(value or "")
    try:
        from services.web_profile import get_site_base_url
        base=get_site_base_url().rstrip("/")
    except Exception:
        base=""
    return text.replace("{site_url}",base).replace("{{site_url}}",base)
