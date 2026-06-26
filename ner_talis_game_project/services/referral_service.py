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
    return f"https://t.me/{bot}?start={REF_PREFIX}{code}"


def attach_referral(storage: Any, new_player: dict[str, Any], code: Any) -> bool:
    """Привязать нового игрока к рефереру. Идемпотентно, не самому себе.

    Меняет new_player на месте (referred_by) — вызывать ДО save_new_player —
    и обновляет запись реферера (referral_count + список referrals)."""
    code = parse_referral_code(code)
    if not code or not isinstance(new_player, dict):
        return False
    new_id = referral_code_for(new_player)
    if not new_id or code == new_id:
        return False
    if new_player.get("referred_by"):
        return False
    get_player = getattr(storage, "get_player_by_game_id", None)
    referrer = get_player(code) if callable(get_player) else None
    if not isinstance(referrer, dict):
        return False

    new_player["referred_by"] = code
    referrer["referral_count"] = int(referrer.get("referral_count") or 0) + 1
    refs = referrer.get("referrals")
    refs = refs if isinstance(refs, list) else []
    if new_id not in refs:
        refs.append(new_id)
    referrer["referrals"] = refs
    update_player = getattr(storage, "update_player", None)
    if callable(update_player):
        try:
            update_player(referrer)
        except Exception:
            pass
    return True


def referral_summary(player: dict[str, Any] | None) -> dict[str, Any]:
    """Данные для профиля: код, ссылка, число приглашённых, кем приглашён."""
    player = player or {}
    return {
        "code": referral_code_for(player),
        "link": build_telegram_link(player),
        "count": int(player.get("referral_count") or 0),
        "referredBy": str(player.get("referred_by") or ""),
    }
