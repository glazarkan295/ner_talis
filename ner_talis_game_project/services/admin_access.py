"""Проверка доступа к административным командам Telegram/VK.

Админ-команды принимаются только из заранее указанного админ-чата/беседы
и только от пользователей, перечисленных в переменных окружения.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AdminAccessResult:
    allowed: bool
    reason: str = ""


def _clean_env_value(name: str, value: str | None) -> str:
    if not value:
        return ""

    cleaned = value.strip().strip("\"'")
    prefix = f"{name}="
    if cleaned.startswith(prefix):
        cleaned = cleaned[len(prefix):].strip()
    return cleaned


def _parse_id_set(name: str) -> set[str]:
    raw = _clean_env_value(name, os.getenv(name))
    if not raw:
        return set()

    return {
        chunk.strip()
        for chunk in re.split(r"[,;\s]+", raw)
        if chunk.strip()
    }


def _id_in_config(value: str | int | None, config_name: str) -> bool:
    if value is None:
        return False
    return str(value) in _parse_id_set(config_name)


def check_telegram_admin(chat_id: str | int | None, user_id: str | int | None) -> AdminAccessResult:
    """Проверяет доступ Telegram-админа."""

    if not _parse_id_set("ADMIN_TELEGRAM_CHAT_IDS"):
        return AdminAccessResult(False, "Не настроена переменная ADMIN_TELEGRAM_CHAT_IDS.")

    if not _parse_id_set("ADMIN_TELEGRAM_USER_IDS"):
        return AdminAccessResult(False, "Не настроена переменная ADMIN_TELEGRAM_USER_IDS.")

    if not _id_in_config(chat_id, "ADMIN_TELEGRAM_CHAT_IDS"):
        return AdminAccessResult(False, "Команда доступна только в разрешённом Telegram админ-чате.")

    if not _id_in_config(user_id, "ADMIN_TELEGRAM_USER_IDS"):
        return AdminAccessResult(False, "Пользователь не входит в список Telegram админов.")

    return AdminAccessResult(True)


def check_vk_admin(peer_id: str | int | None, user_id: str | int | None) -> AdminAccessResult:
    """Проверяет доступ VK-админа."""

    if not _parse_id_set("ADMIN_VK_PEER_IDS"):
        return AdminAccessResult(False, "Не настроена переменная ADMIN_VK_PEER_IDS.")

    if not _parse_id_set("ADMIN_VK_USER_IDS"):
        return AdminAccessResult(False, "Не настроена переменная ADMIN_VK_USER_IDS.")

    if not _id_in_config(peer_id, "ADMIN_VK_PEER_IDS"):
        return AdminAccessResult(False, "Команда доступна только в разрешённой VK админ-беседе.")

    if not _id_in_config(user_id, "ADMIN_VK_USER_IDS"):
        return AdminAccessResult(False, "Пользователь не входит в список VK админов.")

    return AdminAccessResult(True)
