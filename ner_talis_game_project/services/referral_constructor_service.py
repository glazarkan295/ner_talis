"""Конструктор правил реферальной системы Telegram/VK (ТЗ 2.0, файл 16)."""
from __future__ import annotations

from typing import Any
from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403

PLATFORMS = ("all", "telegram", "vk")
LINK_TYPES = ("personal", "admin", "event", "promo", "blogger", "guild", "temporary", "single_use", "multiple_use", "service")
REWARD_TYPES = ("currency", "item", "exp", "energy", "skill_points", "stat_points", "effect", "achievement", "title", "reputation", "promo", "access", "special")
TRIGGERS = ("registration_complete", "level_reached", "starter_quest", "play_minutes", "first_mob", "profile_open", "platform_linked", "activity_reached", "manual")

_store = EntityStore(env_var="REFERRAL_CONSTRUCTOR_PATH", default_rel="data/referral_constructor.json",
                     statuses=STATUSES, transitions=TRANSITIONS, initial_status=STATUS_DRAFT)  # noqa: F405
def store() -> EntityStore: return _store
def _num(value: Any) -> float | None:
    try: return float(value)
    except (TypeError, ValueError): return None

def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}; errors: list[str] = []; warnings: list[str] = []
    if not str(data.get("name") or "").strip(): errors.append("Не заполнено название реферального правила.")
    if str(data.get("platform") or "all") not in PLATFORMS: errors.append("Неизвестная платформа.")
    if str(data.get("link_type") or "personal") not in LINK_TYPES: errors.append("Неизвестный тип реферальной ссылки.")
    if str(data.get("trigger") or "registration_complete") not in TRIGGERS: errors.append("Неизвестный триггер награды.")
    if data.get("trigger") == "level_reached" and (_num(data.get("trigger_value")) is None or _num(data.get("trigger_value")) < 1):
        errors.append("Для награды за уровень укажите уровень не меньше 1.")
    for side in ("referrer_rewards", "referred_rewards"):
        for i, reward in enumerate(data.get(side) or [], 1):
            if not isinstance(reward, dict): errors.append(f"Награда {side} #{i}: неверный формат."); continue
            if str(reward.get("type") or "") not in REWARD_TYPES: errors.append(f"Награда {side} #{i}: неизвестный тип.")
            if _num(reward.get("amount")) is None or _num(reward.get("amount")) <= 0: errors.append(f"Награда {side} #{i}: количество должно быть больше нуля.")
    for key in ("per_referrer_limit", "per_referred_limit", "daily_limit", "weekly_limit", "daily_reward_limit", "weekly_reward_limit", "platform_limit", "campaign_limit", "total_limit"):
        if data.get(key) not in (None, "") and (_num(data.get(key)) is None or _num(data.get(key)) < 0): errors.append(f"{key}: лимит не может быть отрицательным.")
    if data.get("enabled") and not (data.get("referrer_rewards") or data.get("referred_rewards")): warnings.append("Активное правило не содержит наград.")
    if data.get("manual_review") and not str((data.get("texts") or {}).get("manual_review") or "").strip(): warnings.append("Для ручной проверки не настроен текст игроку.")
    if data.get("ends_at") and data.get("starts_at") and str(data["ends_at"]) <= str(data["starts_at"]): errors.append("Дата окончания должна быть позже даты начала.")
    return {"ok": not errors, "errors": errors, "warnings": warnings}

def active_rules(platform: str = "all") -> list[dict[str, Any]]:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    out = []
    for env in store().list(status=STATUS_PUBLISHED):  # noqa: F405
        data = env.get("data") or {}
        if not data.get("enabled", True) or str(data.get("platform") or "all") not in ("all", platform): continue
        if data.get("starts_at") and str(data["starts_at"]) > now: continue
        if data.get("ends_at") and str(data["ends_at"]) < now: continue
        out.append({"id": env.get("id"), **data})
    return sorted(out, key=lambda x: int(x.get("priority") or 0), reverse=True)

def preview(data: dict[str, Any]) -> dict[str, Any]:
    return {"title": data.get("name") or "Реферальное правило", "platform": data.get("platform") or "all",
            "trigger": data.get("trigger") or "registration_complete", "referrer_rewards": data.get("referrer_rewards") or [],
            "referred_rewards": data.get("referred_rewards") or [], "texts": data.get("texts") or {}}
