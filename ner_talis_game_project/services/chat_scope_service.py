"""Область игры: личный чат vs общие чаты/беседы (ТЗ «поведение бота в чатах»).

Игровой процесс разрешён только в ЛИЧНОМ чате игрока с ботом. В общих чатах
(группы/супергруппы/беседы) бот не показывает игровые кнопки и меню, не отвечает
на обычные сообщения и реагирует только на отдельно разрешённые команды
(модерация/справка/админ) с проверкой прав. Здесь — чистая, тестируемая логика
классификации; платформенная привязка (Telegram-фильтры, VK peer_id) — в
main_telegram / vk_registration.
"""

from __future__ import annotations

# Короткие ответы для общих чатов (без кнопок).
GROUP_GAME_NOTICE = "Игровые действия доступны только в личном чате с ботом."
NO_PERMISSION_NOTICE = "У вас нет прав для этой команды."

# Игровые команды — работают только в личном чате с ботом.
GAME_COMMANDS = frozenset({
    "start", "profile", "promo", "site_profile", "link", "connect", "city",
    "unstuck", "inventory", "battle", "market", "craft", "menu", "play",
})

# Команды, отдельно разрешённые в общих чатах (помимо любых admin_*):
# справка/правила/идентификация. Всё остальное в группах игнорируется.
GROUP_ALLOWED_COMMANDS = frozenset({"help", "rules", "admin_id", "modhelp"})

# Классификация сообщения в общем чате.
ACTION_ALLOWED = "allowed"   # пропустить к админ/мод-хендлерам (с их проверкой прав)
ACTION_GAME = "game"         # игровая команда в группе → один раз короткий ответ
ACTION_IGNORE = "ignore"     # обычный текст/неизвестная команда → молчать


def normalize_command(text: str | None) -> str:
    """Из «/Profile@MyBot arg» получить «profile». Не команда → ""."""
    value = str(text or "").strip()
    if not value.startswith("/"):
        return ""
    head = value.split()[0][1:]
    head = head.split("@", 1)[0]
    return head.strip().lower()


def is_group_allowed_command(command: str) -> bool:
    """Команда разрешена в общих чатах (админ/модерация/справка)?"""
    cmd = str(command or "").strip().lower()
    return bool(cmd) and (cmd.startswith("admin_") or cmd in GROUP_ALLOWED_COMMANDS)


def is_game_command(command: str) -> bool:
    return str(command or "").strip().lower() in GAME_COMMANDS


def classify_group_message(text: str | None) -> str:
    """Что делать с сообщением в ОБЩЕМ чате (ACTION_*)."""
    command = normalize_command(text)
    if not command:
        return ACTION_IGNORE          # обычный текст — бот молчит (§6)
    if is_group_allowed_command(command):
        return ACTION_ALLOWED         # модерация/справка/админ — пропустить (§4/§9)
    if is_game_command(command):
        return ACTION_GAME            # игровая команда в группе — один ответ (§7)
    return ACTION_IGNORE              # неизвестная команда — молчать (§6)


# --- Платформенные хелперы определения типа чата ----------------------------
def telegram_chat_is_private(chat_type: object) -> bool:
    return str(chat_type or "").strip().lower() == "private"


def telegram_chat_is_group(chat_type: object) -> bool:
    return str(chat_type or "").strip().lower() in {"group", "supergroup"}


def vk_peer_is_group(peer_id: object) -> bool:
    """VK: peer_id бесед (чатов) начинается с 2000000000."""
    try:
        return int(peer_id) >= 2_000_000_000
    except (TypeError, ValueError):
        return False


def vk_peer_is_private(peer_id: object) -> bool:
    try:
        return 0 < int(peer_id) < 2_000_000_000
    except (TypeError, ValueError):
        return False
