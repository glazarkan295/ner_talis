"""Конструктор регистрации (чат-ТЗ «уровни/опыт/регистрация/расы»).

Запись = шаг/опция регистрации: тип шага (согласие/имя/раса/пол/стартовый дар),
подпись, обязательность, порядок, текст. Слой данных + валидация; хранение —
EntityStore (data/registration_constructor.json). Рантайм регистрации —
handlers/registration.py + registration_service.
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403

STEP_TYPES = ("consent", "name", "race", "gender", "starting_gift", "tutorial", "custom")
STEP_TYPE_LABELS = {
    "consent": "Согласие", "name": "Имя", "race": "Раса", "gender": "Пол",
    "starting_gift": "Стартовый дар", "tutorial": "Обучение", "custom": "Своё",
}

_HTML_RE = re.compile(r"<[^>]+>")

_store = EntityStore(
    env_var="REGISTRATION_CONSTRUCTOR_PATH",
    default_rel="data/registration_constructor.json",
    statuses=STATUSES,  # noqa: F405
    transitions=TRANSITIONS,  # noqa: F405
    initial_status=STATUS_DRAFT,  # noqa: F405
)


def store() -> EntityStore:
    return _store


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if str(data.get("entity_type") or "step") == "scenario":
        return _validate_scenario(envelope)
    if not str(data.get("label") or "").strip():
        errors.append("Не заполнена подпись шага.")
    step = str(data.get("step_type") or "").strip()
    if step and step not in STEP_TYPES:
        errors.append(f"Неизвестный тип шага: {step}.")
    order = _num(data.get("order"))
    if data.get("order") not in (None, "") and (order is None or order < 0):
        errors.append("Порядок не может быть отрицательным.")

    for key in ("label", "text"):
        value = str(data.get(key) or "")
        if value and (_HTML_RE.search(value) or "<script" in value.lower()):
            errors.append(f"В поле «{key}» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def _validate_scenario(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}; errors=[]; warnings=[]
    if not str(data.get("name") or data.get("label") or "").strip(): errors.append("Не заполнено название сценария регистрации.")
    if data.get("active") and not (data.get("telegram_enabled") or data.get("vk_enabled") or data.get("test_enabled")): errors.append("Активный сценарий не назначен ни одной платформе.")
    if not data.get("registration_enabled", True) and not str(data.get("closed_text") or "").strip(): errors.append("Для закрытой регистрации нужен текст закрытия.")
    low, high = _num(data.get("name_min_length")), _num(data.get("name_max_length"))
    if low is not None and high is not None and low > high: errors.append("Минимальная длина имени больше максимальной.")
    steps=[row for row in data.get("steps") or [] if isinstance(row,dict)]; ids=set()
    for i,row in enumerate(steps,1):
        sid=str(row.get("id") or "").strip()
        if not sid: errors.append(f"Шаг {i}: нет ID.")
        elif sid in ids: errors.append(f"Шаг {i}: ID повторяется.")
        ids.add(sid)
        if str(row.get("step_type") or "") not in STEP_TYPES: errors.append(f"Шаг {i}: неизвестный тип.")
        if row.get("required") and row.get("skippable"): errors.append(f"Шаг {i}: обязательный шаг нельзя пропустить.")
    for collection,label in (("starting_items","Стартовый предмет"),("starting_skills","Стартовый навык")):
        for i,row in enumerate(data.get(collection) or [],1):
            if isinstance(row,dict) and not str(row.get("item_id") or row.get("skill_id") or row.get("object_id") or "").strip(): errors.append(f"{label} {i}: не указан ID.")
    text_fields=("welcome_text","existing_profile_text","profile_creation_text","name_prompt_text","name_error_text","race_prompt_text","race_description_text","race_confirmation_text","referral_text","starting_items_text","starting_skills_text","starting_location_text","complete_text","registration_error_text","technical_error_text","closed_text")
    for key in text_fields:
        value=str(data.get(key) or "")
        if value and (_HTML_RE.search(value) or "<script" in value.lower()): errors.append(f"В поле «{key}» недопустим HTML.")
    if not steps: warnings.append("В сценарии не настроены шаги регистрации.")
    if data.get("race_required") and not (data.get("available_races") or []): warnings.append("Обязательный выбор расы использует все опубликованные расы.")
    return {"ok":not errors,"errors":errors,"warnings":warnings}


def active_scenario(platform: str) -> dict[str, Any] | None:
    flag={"telegram":"telegram_enabled","vk":"vk_enabled","test":"test_enabled"}.get(str(platform),"test_enabled")
    rows=[]
    for env in store().list(status=STATUS_PUBLISHED):  # noqa: F405
        data=env.get("data") or {}
        if data.get("entity_type")=="scenario" and data.get("active") and data.get(flag): rows.append((int(data.get("priority") or 0),dict(data)))
    rows.sort(key=lambda row:row[0],reverse=True)
    return rows[0][1] if rows else None


def scenario_text(platform: str, key: str, fallback: str) -> str:
    data=active_scenario(platform) or {}
    return str(data.get(key) or fallback)


def preview(data: dict[str, Any]) -> dict[str, Any]:
    steps=sorted([row for row in data.get("steps") or [] if isinstance(row,dict)],key=lambda row:float(row.get("order") or 0))
    return {"name":data.get("name") or data.get("label"),"platforms":[p for p,k in (("telegram","telegram_enabled"),("vk","vk_enabled"),("test","test_enabled")) if data.get(k)],
            "enabled":bool(data.get("registration_enabled",True)),"steps":[{"id":row.get("id"),"label":row.get("label"),"text":row.get("text"),"buttons":row.get("buttons") or []} for row in steps],
            "start":{"items":data.get("starting_items") or [],"skills":data.get("starting_skills") or [],"location":data.get("start_location_id")}}


def apply_starting_setup(player: dict[str, Any], platform: str) -> None:
    data=active_scenario(platform)
    if not data:return
    race=str(player.get("race_id") or "")
    for row in data.get("starting_items") or []:
        if not isinstance(row,dict) or row.get("race_id") not in (None,"",race) or row.get("platform") not in (None,"",platform):continue
        oid=str(row.get("item_id") or row.get("object_id") or "");amount=max(1,int(float(row.get("amount") or 1)))
        if not oid:continue
        if str(row.get("delivery_mode") or "inventory") == "delivery":
            player.setdefault("pending_registration_delivery",[]).append({"item_id":oid,"amount":amount,"quality":row.get("quality"),"bound":bool(row.get("bind"))});continue
        try:
            from services.inventory_service import add_inventory_item
            from services.item_registry import build_inventory_item
            item=build_inventory_item(oid,amount,item_id=oid);item["bound_on_receive"]=bool(row.get("bind"));add_inventory_item(player,item,amount,default_source="registration")
        except Exception:player.setdefault("pending_registration_delivery",[]).append({"item_id":oid,"amount":amount})
    skills=player.setdefault("skills",{}).setdefault("active",[])
    for row in data.get("starting_skills") or []:
        if not isinstance(row,dict) or row.get("race_id") not in (None,"",race):continue
        oid=str(row.get("skill_id") or row.get("object_id") or "")
        if oid and not any(isinstance(x,dict) and str(x.get("id") or "")==oid for x in skills):skills.append({"id":oid,"name":row.get("name") or oid,"permanent":row.get("permanent",True)})
    for field,key in (("current_city","start_city_id"),("current_location","start_location_id"),("location_id","start_sublocation_id"),("current_zone","start_sublocation_id"),("death_camp_id","start_camp_id")):
        value=data.get(key)
        if value:player[field]=value
    player["registration_scenario_id"]=data.get("system_name") or data.get("name")
