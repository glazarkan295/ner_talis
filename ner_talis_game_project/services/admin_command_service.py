"""Единый разбор административных команд для Telegram и VK."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from typing import Any

from services.admin_audit import write_admin_audit
from services.admin_player_service import add_item_to_player, delete_player_profile, reset_player_progress
from services.promo_service import add_promo_code, deactivate_promo_code, import_promo_codes, list_promo_codes

ADMIN_COMMAND_PREFIX = "/admin"


@dataclass(frozen=True)
class AdminCommandResult:
    handled: bool
    text: str


def is_admin_command(text: str) -> bool:
    return str(text or "").strip().startswith(ADMIN_COMMAND_PREFIX)


def admin_help_text() -> str:
    return (
        "Админ-команды Нер-Талис:\n\n"
        "/admin_id — показать ID текущего чата/беседы и пользователя.\n"
        "/admin_help — показать эту справку.\n\n"
        "Промокоды:\n"
        "/admin_promo_add CODE USES REWARD_JSON\n"
        "Пример: /admin_promo_add START100 100 {\"money\":1000,\"items\":[{\"item_id\":\"small_potion\",\"amount\":3}]}\n"
        "/admin_promo_bulk JSON_ARRAY — загрузить сразу несколько промокодов.\n"
        "Пример: /admin_promo_bulk [{\"code\":\"A1\",\"uses_left\":10,\"reward\":{\"money\":500}}]\n"
        "/admin_promo_off CODE — отключить промокод.\n"
        "/admin_promo_list — показать последние промокоды.\n\n"
        "Игроки:\n"
        "/admin_reset_player GAME_ID CONFIRM — обнулить прогресс игрока.\n"
        "/admin_delete_player ID CONFIRM_DELETE — удалить профиль игрока и вернуть его на регистрацию.\n"
        "ID для удаления: GAME_ID, public_id, tg_123, vk_123 или telegram:123.\n"
        "/admin_add_item GAME_ID ITEM_ID AMOUNT QUALITY — добавить простой предмет.\n"
        "/admin_add_item_json GAME_ID ITEM_JSON — добавить предмет с полными полями.\n\n"
        "Все опасные действия пишутся в audit log и делают backup профиля игрока."
    )


def _parse_parts(text: str) -> list[str]:
    try:
        return shlex.split(text)
    except ValueError:
        return str(text).strip().split()


def _split_command_and_payload(text: str) -> tuple[list[str], str]:
    stripped = str(text or "").strip()
    parts = _parse_parts(stripped)
    if not parts:
        return [], ""
    command = parts[0]
    payload = stripped[len(command):].strip()
    return parts, payload


def _json_after_tokens(text: str, token_count: int) -> str:
    stripped = str(text or "").strip()
    index = 0
    for _ in range(token_count):
        while index < len(stripped) and stripped[index].isspace():
            index += 1
        while index < len(stripped) and not stripped[index].isspace():
            index += 1
    return stripped[index:].strip()


def execute_admin_command(*, text: str, storage: Any, platform: str, admin_user_id: str | int) -> AdminCommandResult:
    parts, _payload = _split_command_and_payload(text)
    if not parts:
        return AdminCommandResult(False, "")

    command = parts[0]

    if command == "/admin_help":
        return AdminCommandResult(True, admin_help_text())

    if command == "/admin_promo_add":
        if len(parts) < 4:
            return AdminCommandResult(True, "Формат: /admin_promo_add CODE USES REWARD_JSON")
        code = parts[1]
        try:
            uses_left = int(parts[2])
            reward = json.loads(_json_after_tokens(text, 3))
            promo = add_promo_code(code=code, uses_left=uses_left, reward=reward)
        except Exception as exc:
            return AdminCommandResult(True, f"Не удалось создать промокод: {exc}")
        write_admin_audit(platform=platform, admin_user_id=admin_user_id, command=text, action="promo_add", details={"code": promo["code"], "uses_left": uses_left, "reward": reward})
        return AdminCommandResult(True, f"Промокод {promo['code']} создан. Использований: {uses_left}.")

    if command == "/admin_promo_bulk":
        raw_json = _json_after_tokens(text, 1)
        if not raw_json:
            return AdminCommandResult(True, "Формат: /admin_promo_bulk JSON_ARRAY")
        try:
            items = json.loads(raw_json)
            if not isinstance(items, list):
                return AdminCommandResult(True, "JSON должен быть массивом промокодов.")
            imported = import_promo_codes(items)
        except Exception as exc:
            return AdminCommandResult(True, f"Не удалось импортировать промокоды: {exc}")
        write_admin_audit(platform=platform, admin_user_id=admin_user_id, command=text, action="promo_bulk", details={"count": imported})
        return AdminCommandResult(True, f"Загружено промокодов: {imported}.")

    if command == "/admin_promo_off":
        if len(parts) < 2:
            return AdminCommandResult(True, "Формат: /admin_promo_off CODE")
        code = parts[1]
        if not deactivate_promo_code(code):
            return AdminCommandResult(True, "Промокод не найден.")
        write_admin_audit(platform=platform, admin_user_id=admin_user_id, command=text, action="promo_off", details={"code": code.upper()})
        return AdminCommandResult(True, f"Промокод {code.upper()} отключён.")

    if command == "/admin_promo_list":
        promos = list_promo_codes(limit=20)
        if not promos:
            return AdminCommandResult(True, "Промокодов пока нет.")
        lines = ["Последние промокоды:"]
        for promo in promos:
            status = "активен" if promo.get("active") else "отключён"
            lines.append(f"{promo.get('code')} — {status}, использований осталось: {promo.get('uses_left')}")
        return AdminCommandResult(True, "\n".join(lines))

    if command == "/admin_reset_player":
        if len(parts) < 3:
            return AdminCommandResult(True, "Формат: /admin_reset_player GAME_ID CONFIRM")
        game_id, confirm = parts[1], parts[2]
        if confirm != "CONFIRM":
            return AdminCommandResult(True, "Для сброса нужно явно написать CONFIRM третьим аргументом.")
        ok, message, _player = reset_player_progress(storage, game_id)
        if ok:
            write_admin_audit(platform=platform, admin_user_id=admin_user_id, command=text, action="reset_player", details={"game_id": game_id})
        return AdminCommandResult(True, message)

    if command == "/admin_delete_player":
        if len(parts) < 3:
            return AdminCommandResult(True, "Формат: /admin_delete_player ID CONFIRM_DELETE")
        identifier, confirm = parts[1], parts[2]
        if confirm != "CONFIRM_DELETE":
            return AdminCommandResult(True, "Для удаления нужно явно написать CONFIRM_DELETE третьим аргументом.")
        ok, message, player = delete_player_profile(storage, identifier)
        if ok:
            write_admin_audit(
                platform=platform,
                admin_user_id=admin_user_id,
                command=text,
                action="delete_player",
                details={"identifier": identifier, "game_id": player.get("game_id") if player else None},
            )
        return AdminCommandResult(True, message)

    if command == "/admin_add_item":
        if len(parts) < 5:
            return AdminCommandResult(True, "Формат: /admin_add_item GAME_ID ITEM_ID AMOUNT QUALITY")
        game_id, item_id = parts[1], parts[2]
        try:
            amount = int(parts[3])
        except ValueError:
            return AdminCommandResult(True, "AMOUNT должен быть числом.")
        quality = parts[4]
        ok, message, _player = add_item_to_player(storage, game_id=game_id, item_id=item_id, amount=amount, quality=quality)
        if ok:
            write_admin_audit(platform=platform, admin_user_id=admin_user_id, command=text, action="add_item", details={"game_id": game_id, "item_id": item_id, "amount": amount, "quality": quality})
        return AdminCommandResult(True, message)

    if command == "/admin_add_item_json":
        if len(parts) < 3:
            return AdminCommandResult(True, "Формат: /admin_add_item_json GAME_ID ITEM_JSON")
        game_id = parts[1]
        try:
            item_data = json.loads(_json_after_tokens(text, 2))
            if not isinstance(item_data, dict):
                return AdminCommandResult(True, "ITEM_JSON должен быть JSON-объектом.")
            item_id = str(item_data.get("item_id") or item_data.get("id") or "admin_item")
            amount = int(item_data.get("amount", 1))
            quality = str(item_data.get("quality", "обычный"))
        except Exception as exc:
            return AdminCommandResult(True, f"Не удалось разобрать ITEM_JSON: {exc}")
        ok, message, _player = add_item_to_player(storage, game_id=game_id, item_id=item_id, amount=amount, quality=quality, item_data=item_data)
        if ok:
            write_admin_audit(platform=platform, admin_user_id=admin_user_id, command=text, action="add_item_json", details={"game_id": game_id, "item_id": item_id, "amount": amount})
        return AdminCommandResult(True, message)

    if is_admin_command(text):
        return AdminCommandResult(True, "Неизвестная админ-команда. Введите /admin_help.")

    return AdminCommandResult(False, "")
