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
    return f"https://vk.me/{screen}?ref={REF_PREFIX}{code}"


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
    refs = referrer.get("referrals")
    refs = refs if isinstance(refs, list) else []
    if new_id in refs:
        return False  # уже учтён — идемпотентно, без повторного инкремента
    refs.append(new_id)
    referrer["referrals"] = refs
    referrer["referral_count"] = int(referrer.get("referral_count") or 0) + 1
    update_player = getattr(storage, "update_player", None)
    if callable(update_player):
        try:
            update_player(referrer)
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
