"""Published race selection/restrictions and confirmed race change (§22–§24)."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any


def definition(race_id: str) -> dict[str, Any] | None:
    from services.race_constructor_service import published_definition
    return published_definition(race_id)


def restriction_error(player: dict[str, Any], object_type: str, object_id: str) -> str | None:
    data = definition(str(player.get("race_id") or "")) or {}
    field = {"skill": "forbidden_skills", "item": "forbidden_items", "location": "forbidden_locations", "quest": "forbidden_quests"}.get(object_type)
    if field and str(object_id) in {str(x) for x in data.get(field) or []}:
        return str(data.get("restriction_text") or f"Раса не позволяет использовать: {object_id}.")
    return None


def request_change(player: dict[str, Any], target_race_id: str, *, method: str = "service") -> dict[str, Any]:
    target = definition(target_race_id)
    if not target: raise ValueError("Целевая раса не опубликована или не найдена.")
    current = definition(str(player.get("race_id") or "")) or {}
    if target_race_id == str(player.get("race_id") or ""): raise ValueError("Эта раса уже выбрана.")
    if not target.get("change_allowed"):
        raise ValueError(str(target.get("change_denied_text") or "Смена на эту расу запрещена."))
    allowed = {"admin": "change_via_admin", "item": "change_via_item", "quest": "change_via_quest", "service": "change_via_service"}
    if not target.get(allowed.get(method, "change_via_service")):
        raise ValueError(str(target.get("change_denied_text") or "Этот способ смены расы запрещён."))
    warning = str(target.get("change_warning_text") or current.get("change_warning_text") or "⚠️ Смена расы изменит постоянные бонусы персонажа.")
    token = secrets.token_urlsafe(24)
    player["pending_race_change"] = {"target_race_id": target_race_id, "method": method, "token": token,
                                     "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}
    return {"target_race_id": target_race_id, "target_name": target.get("player_name") or target.get("race_name") or target_race_id,
            "warning": warning, "confirmation_token": token, "cost": max(0, int(float(target.get("change_cost") or 0)))}


def confirm_change(player: dict[str, Any], token: str) -> dict[str, Any]:
    pending = player.get("pending_race_change") if isinstance(player.get("pending_race_change"), dict) else {}
    if not token or not secrets.compare_digest(str(pending.get("token") or ""), str(token)):
        raise ValueError("Неверное подтверждение смены расы.")
    try: expired = datetime.now(timezone.utc) >= datetime.fromisoformat(str(pending.get("expires_at") or ""))
    except ValueError: expired = True
    if expired: player.pop("pending_race_change", None); raise ValueError("Подтверждение смены расы истекло.")
    target_id = str(pending.get("target_race_id") or ""); target = definition(target_id)
    if not target or not target.get("change_allowed"): raise ValueError("Смена расы больше недоступна.")
    cost = max(0, int(float(target.get("change_cost") or 0))); money_key = "money_copper" if "money_copper" in player else "money"
    if int(player.get(money_key) or 0) < cost: raise ValueError("Недостаточно монет для смены расы.")
    old_id = str(player.get("race_id") or "")
    try:
        from services.economy_runtime import change,service_price
        cost=service_price("race_change",cost,player,{"race_id":target_id});change(player,"copper",-cost,operation="race_change",source="race",source_id=target_id)
    except ImportError:player[money_key]=int(player.get(money_key) or 0)-cost
    player["race_id"] = target_id; player["race_name"] = target.get("player_name") or target.get("race_name") or target_id
    if not target.get("preserve_progress", True):
        percent = max(0, min(100, int(float(target.get("reset_progress_percent") or 0))))
        player["experience"] = max(0, int(player.get("experience") or 0) * (100 - percent) // 100)
    from services.race_bonus_service import sync_passive_effects
    sync_passive_effects(player)
    player.setdefault("race_change_history", []).append({"at": datetime.now(timezone.utc).isoformat(), "from": old_id, "to": target_id, "method": pending.get("method"), "cost": cost})
    player.pop("pending_race_change", None)
    return {"old_race_id": old_id, "race_id": target_id, "message": str(target.get("change_success_text") or "Раса успешно изменена."), "cost": cost}
