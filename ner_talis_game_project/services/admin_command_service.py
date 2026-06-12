"""Единый разбор административных команд для Telegram и VK."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from typing import Any

from services.admin_audit import write_admin_audit
from services.admin_panel_service import create_admin_panel_activation_token, build_admin_panel_url
from services.admin_player_service import (
    add_experience_to_player,
    add_item_to_player,
    add_money_to_player,
    add_skill_points_to_player,
    add_stat_points_to_player,
    delete_player_profile,
    find_players,
    format_player_admin_summary,
    kick_player_profile_sessions,
    reset_player_progress,
)
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
        "/admin_help — показать эту справку.\n"
        "/admin_panel — получить одноразовую ссылку в защищённую админ-панель сайта.\n\n"
        "Старые текстовые админ-команды оставлены как аварийный режим; основная работа теперь через админ-панель.\n\n"
        "Промокоды:\n"
        "/admin_promo_add CODE USES REWARD_JSON\n"
        "Пример: /admin_promo_add START100 100 {\"money\":1000,\"items\":[{\"item_id\":\"simple_healing_potion\",\"amount\":3}]}\n"
        "Пример опыта: /admin_promo_add EXP4500 100 {\"experience\":4500}\n"
        "/admin_promo_bulk JSON_ARRAY — загрузить сразу несколько промокодов.\n"
        "Пример: /admin_promo_bulk [{\"code\":\"A1\",\"uses_left\":10,\"reward\":{\"money\":500}}]\n"
        "/admin_promo_off CODE — отключить промокод.\n"
        "/admin_promo_list — показать последние промокоды.\n\n"
        "Игроки:\n"
        "/admin_find_player QUERY — найти игрока по game_id, имени, public_id, Telegram/VK id.\n"
        "/admin_player_info GAME_ID — показать короткую админ-карточку игрока.\n"
        "/admin_add_money GAME_ID AMOUNT CONFIRM — добавить/списать медные монеты.\n"
        "/admin_add_experience GAME_ID AMOUNT CONFIRM — начислить крупицы опыта, 1 крупица = 1 опыт.\n"
        "/admin_add_stat_points GAME_ID AMOUNT CONFIRM — добавить/списать очки характеристик, 1 к 1.\n"
        "/admin_add_skill_points GAME_ID AMOUNT CONFIRM — добавить/списать очки навыков, 1 к 1.\n"
        "/admin_kick_profile_sessions GAME_ID CONFIRM — отключить активные web-сессии профиля.\n"
        "/admin_reset_player GAME_ID CONFIRM — обнулить прогресс игрока.\n"
        "/admin_delete_player NT-XXXXXXXXXX CONFIRM_DELETE — полностью удалить профиль игрока и вернуть его на регистрацию.\n"
        "Удаление работает только по игровому ID вида NT-XXXXXXXXXX.\n"
        "/admin_add_item GAME_ID ITEM_ID AMOUNT QUALITY — добавить простой предмет.\n"
        "/admin_add_item_json GAME_ID ITEM_JSON — добавить предмет с полными полями.\n\n"
        "Все опасные действия пишутся в audit log. Сброс делает backup, а удаление профиля выполняется без backup старого персонажа."
    )


def _normalize_command_token(command: str) -> str:
    normalized = str(command or "").strip()
    if "@" in normalized:
        normalized = normalized.split("@", 1)[0]
    return normalized


def _looks_like_placeholder(identifier: str) -> bool:
    return str(identifier or "").strip().upper() in {
        "ID",
        "GAME_ID",
        "PLAYER_ID",
        "PUBLIC_ID",
        "TG_ID",
        "VK_ID",
    }


def _parse_parts(text: str) -> list[str]:
    try:
        return shlex.split(text)
    except ValueError:
        return str(text).strip().split()


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
    parts = _parse_parts(text)
    if not parts:
        return AdminCommandResult(False, "")

    command = _normalize_command_token(parts[0])

    if command == "/admin_help":
        return AdminCommandResult(True, admin_help_text())

    if command == "/admin_panel":
        try:
            token = create_admin_panel_activation_token(
                storage,
                platform=platform,
                admin_user_id=admin_user_id,
            )
            url = build_admin_panel_url(token)
        except Exception as exc:
            return AdminCommandResult(True, f"Не удалось создать ссылку админ-панели: {exc}")
        write_admin_audit(
            platform=platform,
            admin_user_id=admin_user_id,
            command=text,
            action="admin_panel_token",
            details={"scope": "admin_panel"},
        )
        return AdminCommandResult(
            True,
            "🛡 Админ-панель Нер-Талис готова.\n\n"
            f"Открыть: {url}\n\n"
            "Ссылка одноразовая: после первой активации повторно по ней войти нельзя. "
            "Новая ссылка отключит старую активную админ-сессию этого админа.",
        )

    if command == "/admin_promo_add":
        if len(parts) < 4:
            return AdminCommandResult(True, "Формат: /admin_promo_add CODE USES REWARD_JSON")
        code = parts[1]
        try:
            uses_left = int(parts[2])
            reward = json.loads(_json_after_tokens(text, 3))
            promo = add_promo_code(code=code, uses_left=uses_left, reward=reward, storage=storage)
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
            imported = import_promo_codes(items, storage=storage)
        except Exception as exc:
            return AdminCommandResult(True, f"Не удалось импортировать промокоды: {exc}")
        write_admin_audit(platform=platform, admin_user_id=admin_user_id, command=text, action="promo_bulk", details={"count": imported})
        return AdminCommandResult(True, f"Загружено промокодов: {imported}.")

    if command == "/admin_promo_off":
        if len(parts) < 2:
            return AdminCommandResult(True, "Формат: /admin_promo_off CODE")
        code = parts[1]
        if not deactivate_promo_code(code, storage=storage):
            return AdminCommandResult(True, "Промокод не найден.")
        write_admin_audit(platform=platform, admin_user_id=admin_user_id, command=text, action="promo_off", details={"code": code.upper()})
        return AdminCommandResult(True, f"Промокод {code.upper()} отключён.")

    if command == "/admin_promo_list":
        promos = list_promo_codes(limit=20, storage=storage)
        if not promos:
            return AdminCommandResult(True, "Промокодов пока нет.")
        lines = ["Последние промокоды:"]
        for promo in promos:
            status = "активен" if promo.get("active") else "отключён"
            lines.append(f"{promo.get('code')} — {status}, использований осталось: {promo.get('uses_left')}")
        return AdminCommandResult(True, "\n".join(lines))


    if command == "/admin_find_player":
        if len(parts) < 2:
            return AdminCommandResult(True, "Формат: /admin_find_player QUERY")
        query = _json_after_tokens(text, 1) or parts[1]
        matches = find_players(storage, query, limit=10)
        if not matches:
            return AdminCommandResult(True, "Игроки не найдены.")
        lines = [f"Найдено игроков: {len(matches)}"]
        for player in matches:
            linked = player.get("linked_accounts") if isinstance(player.get("linked_accounts"), dict) else {}
            linked_text = ", ".join(f"{k}:{v}" for k, v in linked.items() if v) or "нет"
            lines.append(
                f"- {player.get('game_id') or player.get('id')} | {player.get('name') or 'без имени'} | "
                f"ур. {player.get('level', 1)} | {linked_text}"
            )
        return AdminCommandResult(True, "\n".join(lines))

    if command == "/admin_player_info":
        if len(parts) < 2:
            return AdminCommandResult(True, "Формат: /admin_player_info GAME_ID")
        game_id = parts[1]
        if _looks_like_placeholder(game_id):
            return AdminCommandResult(True, "GAME_ID — это пример. Укажи настоящий игровой ID игрока вида NT-XXXXXXXXXX.")
        matches = find_players(storage, game_id, limit=1)
        if not matches:
            return AdminCommandResult(True, f"Игрок {game_id} не найден.")
        return AdminCommandResult(True, format_player_admin_summary(matches[0]))

    if command == "/admin_add_money":
        if len(parts) < 4:
            return AdminCommandResult(True, "Формат: /admin_add_money GAME_ID AMOUNT CONFIRM")
        game_id, raw_amount, confirm = parts[1], parts[2], parts[3]
        if _looks_like_placeholder(game_id):
            return AdminCommandResult(True, "GAME_ID — это пример. Укажи настоящий игровой ID игрока вида NT-XXXXXXXXXX.")
        if confirm != "CONFIRM":
            return AdminCommandResult(True, "Для изменения монет нужно явно написать CONFIRM четвёртым аргументом.")
        try:
            amount = int(raw_amount)
        except ValueError:
            return AdminCommandResult(True, "AMOUNT должен быть целым числом. Для списания можно указать отрицательное число.")
        ok, message, player = add_money_to_player(storage, game_id=game_id, amount=amount)
        if ok:
            write_admin_audit(
                platform=platform,
                admin_user_id=admin_user_id,
                command=text,
                action="add_money",
                details={"game_id": player.get("game_id") if player else game_id, "amount": amount},
            )
        return AdminCommandResult(True, message)

    if command in {"/admin_add_experience", "/admin_add_exp"}:
        if len(parts) < 4:
            return AdminCommandResult(True, "Формат: /admin_add_experience GAME_ID AMOUNT CONFIRM")
        game_id, raw_amount, confirm = parts[1], parts[2], parts[3]
        if _looks_like_placeholder(game_id):
            return AdminCommandResult(True, "GAME_ID — это пример. Укажи настоящий игровой ID игрока вида NT-XXXXXXXXXX.")
        if confirm != "CONFIRM":
            return AdminCommandResult(True, "Для начисления опыта нужно явно написать CONFIRM четвёртым аргументом.")
        try:
            amount = int(raw_amount)
        except ValueError:
            return AdminCommandResult(True, "AMOUNT должен быть целым положительным числом.")
        ok, message, player = add_experience_to_player(storage, game_id=game_id, amount=amount)
        if ok:
            write_admin_audit(
                platform=platform,
                admin_user_id=admin_user_id,
                command=text,
                action="add_experience",
                details={"game_id": player.get("game_id") if player else game_id, "amount": amount},
            )
        return AdminCommandResult(True, message)

    if command in {"/admin_add_stat_points", "/admin_add_attribute_points"}:
        if len(parts) < 4:
            return AdminCommandResult(True, "Формат: /admin_add_stat_points GAME_ID AMOUNT CONFIRM")
        game_id, raw_amount, confirm = parts[1], parts[2], parts[3]
        if _looks_like_placeholder(game_id):
            return AdminCommandResult(True, "GAME_ID — это пример. Укажи настоящий игровой ID игрока вида NT-XXXXXXXXXX.")
        if confirm != "CONFIRM":
            return AdminCommandResult(True, "Для изменения очков характеристик нужно явно написать CONFIRM четвёртым аргументом.")
        try:
            amount = int(raw_amount)
        except ValueError:
            return AdminCommandResult(True, "AMOUNT должен быть целым числом. Для списания можно указать отрицательное число.")
        ok, message, player = add_stat_points_to_player(storage, game_id=game_id, amount=amount)
        if ok:
            write_admin_audit(
                platform=platform,
                admin_user_id=admin_user_id,
                command=text,
                action="add_stat_points",
                details={"game_id": player.get("game_id") if player else game_id, "amount": amount},
            )
        return AdminCommandResult(True, message)

    if command == "/admin_add_skill_points":
        if len(parts) < 4:
            return AdminCommandResult(True, "Формат: /admin_add_skill_points GAME_ID AMOUNT CONFIRM")
        game_id, raw_amount, confirm = parts[1], parts[2], parts[3]
        if _looks_like_placeholder(game_id):
            return AdminCommandResult(True, "GAME_ID — это пример. Укажи настоящий игровой ID игрока вида NT-XXXXXXXXXX.")
        if confirm != "CONFIRM":
            return AdminCommandResult(True, "Для изменения очков навыков нужно явно написать CONFIRM четвёртым аргументом.")
        try:
            amount = int(raw_amount)
        except ValueError:
            return AdminCommandResult(True, "AMOUNT должен быть целым числом. Для списания можно указать отрицательное число.")
        ok, message, player = add_skill_points_to_player(storage, game_id=game_id, amount=amount)
        if ok:
            write_admin_audit(
                platform=platform,
                admin_user_id=admin_user_id,
                command=text,
                action="add_skill_points",
                details={"game_id": player.get("game_id") if player else game_id, "amount": amount},
            )
        return AdminCommandResult(True, message)

    if command == "/admin_kick_profile_sessions":
        if len(parts) < 3:
            return AdminCommandResult(True, "Формат: /admin_kick_profile_sessions GAME_ID CONFIRM")
        game_id, confirm = parts[1], parts[2]
        if _looks_like_placeholder(game_id):
            return AdminCommandResult(True, "GAME_ID — это пример. Укажи настоящий игровой ID игрока вида NT-XXXXXXXXXX.")
        if confirm != "CONFIRM":
            return AdminCommandResult(True, "Для отключения сессий нужно явно написать CONFIRM третьим аргументом.")
        ok, message, deleted = kick_player_profile_sessions(storage, game_id=game_id)
        if ok:
            write_admin_audit(
                platform=platform,
                admin_user_id=admin_user_id,
                command=text,
                action="kick_profile_sessions",
                details={"game_id": game_id, "deleted_sessions": deleted},
            )
        return AdminCommandResult(True, message)

    if command == "/admin_reset_player":
        if len(parts) < 3:
            return AdminCommandResult(True, "Формат: /admin_reset_player GAME_ID CONFIRM")
        game_id, confirm = parts[1], parts[2]
        if _looks_like_placeholder(game_id):
            return AdminCommandResult(True, "GAME_ID — это пример. Укажи настоящий ID игрока, например NT-XXXXXXXXXX, tg_123456 или vk_123456.")
        if confirm != "CONFIRM":
            return AdminCommandResult(True, "Для сброса нужно явно написать CONFIRM третьим аргументом.")
        ok, message, _player = reset_player_progress(storage, game_id)
        if ok:
            write_admin_audit(platform=platform, admin_user_id=admin_user_id, command=text, action="reset_player", details={"game_id": game_id})
        return AdminCommandResult(True, message)

    if command == "/admin_delete_player":
        if len(parts) < 3:
            return AdminCommandResult(True, "Формат: /admin_delete_player NT-XXXXXXXXXX CONFIRM_DELETE")
        identifier, confirm = parts[1], parts[2]
        if _looks_like_placeholder(identifier):
            return AdminCommandResult(True, "GAME_ID — это пример. Укажи настоящий игровой ID игрока вида NT-XXXXXXXXXX.")
        if confirm != "CONFIRM_DELETE":
            return AdminCommandResult(True, "Для удаления нужно явно написать CONFIRM_DELETE третьим аргументом.")
        ok, message, player = delete_player_profile(storage, identifier)
        if ok:
            write_admin_audit(
                platform=platform,
                admin_user_id=admin_user_id,
                command=text,
                action="delete_player_hard",
                details={"game_id": player.get("game_id") if player else identifier},
            )
        return AdminCommandResult(True, message)

    if command == "/admin_add_item":
        if len(parts) < 5:
            return AdminCommandResult(True, "Формат: /admin_add_item GAME_ID ITEM_ID AMOUNT QUALITY")
        game_id, item_id = parts[1], parts[2]
        if _looks_like_placeholder(game_id):
            return AdminCommandResult(True, "GAME_ID — это пример. Укажи настоящий ID игрока.")
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
