"""Передача предметов между игроками через городского гонца.

Игрок оформляет посылку на сайте: получатель (ник/ID), предметы из инвентаря
(и/или монеты), короткое письмо. Предметы и стоимость доставки списываются
сразу. Гонец доставляет посылку через 10–15 минут фоновым воркером:

* успех — получатель получает предметы/монеты и сообщения гонца;
* шанс 0,01% — посылку крадут (предметы теряются, отправитель получает весть);
* шанс 0,1% — посылка уходит случайному игроку (отправитель получает весть).

Очередь посылок хранится в отдельном JSON-файле (как портовый рынок) под
потоковым + межпроцессным файловым локом, поэтому доставка не дублируется и не
затирает свежие изменения игроков (получатели перезагружаются перед доставкой).
"""

from __future__ import annotations

import json
import os
import random
import threading
import uuid
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

try:  # POSIX file locking (отсутствует на Windows-разработке)
    import fcntl
except Exception:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

from project_paths import project_path, resolve_project_path
from services.currency import format_money, format_price
from services.derived_stats_service import safe_int
from services.inventory_service import add_inventory_item, recalculate_inventory_overflow

# --- Параметры доставки -----------------------------------------------------
DELIVERY_MIN_MINUTES = 10
DELIVERY_MAX_MINUTES = 15
LETTER_MAX_LENGTH = 30
BASE_COST_COPPER = 10
COST_LEVEL_FACTOR = 1.3  # стоимость = 10 * (уровень * 1,3)
STOLEN_CHANCE_PERCENT = 0.01
MISDELIVERY_CHANCE_PERCENT = 0.1
MAX_DELIVERY_ATTEMPTS = 5

# --- Тексты (предоставлены дизайном дословно) -------------------------------
WARNING_TEXT = (
    "Вы можете отправить предметы другому игроку через городского гонца.\n"
    "Гонец доставит посылку в течение 10–15 минут.\n"
    "Стоимость отправки: {delivery_cost}.\n"
    "Перед отправкой выберите получателя по нику или игровому ID, добавьте "
    "предметы из инвентаря и укажите их количество.\n"
    "Можно приложить короткое сообщение до 30 символов — оно будет доставлено "
    "вместе с посылкой.\n"
    "⚠️ После отправки предметы и стоимость доставки будут списаны сразу. "
    "Дорога не всегда безопасна: в редких случаях посылка может быть потеряна, "
    "украдена или доставлена не тому человеку."
)

SENDER_CONFIRM_TEXT = (
    "📦 Посылка передана гонцу.\n\n"
    "Гонец забрал вашу посылку и отправился к игроку {receiver_name}.\n"
    "Ожидаемое время доставки: 10–15 минут.\n\n"
    "Стоимость доставки: {delivery_cost}."
)

RECEIVER_COURIER_REPLY_TEXT = (
    "🏃‍♂️ Гонец останавливается рядом, переводит дыхание и протягивает вам "
    "свёрток.\n\n"
    "— Эй, это вы {receiver_name}? Тогда посылка для вас. Передал игрок "
    "{sender_name}. Сказали доставить лично в руки, без лишних вопросов."
)

RECEIVER_CONTENTS_TEXT = (
    "📦 Вы получили посылку от игрока {sender_name}.\n\n"
    "В посылке находилось:\n\n"
    "{items_list}"
)

RECEIVER_LETTER_SUFFIX = (
    "\n\nВнутри также лежало короткое письмо:\n\n"
    "✉️ «{letter_text}»"
)

SENDER_STOLEN_TEXT = (
    "⚠️ Посылка не была доставлена.\n\n"
    "Позже к вам вернулся потрёпанный гонец. Одежда порвана, на лице следы "
    "пыли и крови, а в руках — пусто.\n\n"
    "— Простите… На дороге нас перехватили. Я пытался уйти через старую тропу, "
    "но их было слишком много. Посылку отобрали.\n\n"
    "Ваша посылка для игрока {receiver_name} была украдена по дороге.\n"
    "Отправленные предметы вернуть не удалось."
)

SENDER_MISDELIVERED_TEXT = (
    "⚠️ Посылка доставлена не тому получателю.\n\n"
    "Гонец вернулся слишком довольный для человека, который явно что-то "
    "перепутал.\n\n"
    "— Доставил, как просили! Только… кажется, имя было похоже. Или ID. В общем, "
    "человек посылку принял уверенно.\n\n"
    "Ваша посылка для игрока {receiver_name} по ошибке была доставлена другому "
    "игроку.\n"
    "Вернуть отправленные предметы не удалось."
)

RANDOM_RECIPIENT_TEXT = (
    "🏃‍♂️ Гонец подходит к вам и протягивает свёрток.\n\n"
    "— Посылка для вас. По крайней мере, так мне сказали. Имя вроде сходится… "
    "или почти сходится. Забирайте, пока я не начал сомневаться.\n\n"
    "📦 Вы получили чужую посылку.\n\n"
    "В посылке находилось:\n\n"
    "{items_list}"
)

RANDOM_RECIPIENT_LETTER_SUFFIX = (
    "\n\nЕсли внутри было письмо, на нём написано:\n\n"
    "✉️ «{letter_text}»"
)

# Внутрипроцессная защита потоков + межпроцессный файловый лок POSIX.
_TRANSFERS_LOCK = threading.Lock()


class CourierError(Exception):
    """Ошибка оформления посылки с человекочитаемым сообщением для игрока."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def transfers_path() -> Path:
    override = os.getenv("COURIER_TRANSFERS_PATH")
    if override:
        return resolve_project_path(override)
    return project_path("data", "courier_transfers.json")


def _load_transfers() -> list[dict[str, Any]]:
    path = transfers_path()
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        data = data.get("transfers")
    return [entry for entry in data if isinstance(entry, dict)] if isinstance(data, list) else []


def _save_transfers(transfers: list[dict[str, Any]]) -> None:
    path = transfers_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as file:
        json.dump({"transfers": transfers}, file, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


@contextmanager
def _transfers_file_lock() -> Iterator[None]:
    if fcntl is None:
        yield
        return
    path = transfers_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def delivery_cost_copper(level: Any) -> int:
    """Стоимость доставки в меди: 10 * (уровень * 1,3), не меньше базовой."""
    level_value = max(1, safe_int(level, 1))
    cost = int(round(BASE_COST_COPPER * level_value * COST_LEVEL_FACTOR))
    return max(BASE_COST_COPPER, cost)


def courier_warning_text(level: Any) -> str:
    return WARNING_TEXT.format(delivery_cost=format_price(delivery_cost_copper(level)))


# --- Поиск игроков ----------------------------------------------------------
def _all_players(storage: Any) -> dict[str, dict[str, Any]]:
    try:
        data = storage.load()
    except Exception:
        return {}
    players = data.get("players") if isinstance(data, dict) else None
    if not isinstance(players, dict):
        return {}
    return {str(gid): pl for gid, pl in players.items() if isinstance(pl, dict)}


def find_player_by_query(storage: Any, query: str) -> dict[str, Any] | None:
    text = str(query or "").strip()
    if not text:
        return None
    by_id = getattr(storage, "get_player_by_game_id", None)
    if callable(by_id):
        found = by_id(text)
        if isinstance(found, dict):
            return found
    folded = text.casefold()
    for player in _all_players(storage).values():
        if str(player.get("name", "")).casefold() == folded:
            return player
        if str(player.get("game_id") or player.get("id") or "").casefold() == folded:
            return player
    return None


def search_players(storage: Any, query: str, limit: int = 8) -> list[dict[str, Any]]:
    """Подсказки получателей по нику/ID (для строки поиска игрока)."""
    text = str(query or "").strip().casefold()
    if not text:
        return []
    matches: list[dict[str, Any]] = []
    for game_id, player in _all_players(storage).items():
        name = str(player.get("name", ""))
        if text in name.casefold() or text in game_id.casefold():
            matches.append({
                "gameId": game_id,
                "name": name or "Безымянный",
                "level": safe_int(player.get("level"), 1),
            })
        if len(matches) >= limit:
            break
    return matches


# --- Форматирование содержимого посылки -------------------------------------
def format_items_list(items: list[dict[str, Any]], coins_copper: int = 0) -> str:
    lines: list[str] = []
    index = 1
    for entry in items:
        name = str(entry.get("name") or "Предмет")
        amount = max(1, safe_int(entry.get("amount"), 1))
        lines.append(f"{index}.{name} ×{amount}")
        index += 1
    if coins_copper > 0:
        lines.append(f"{index}.Монеты: {format_money(coins_copper)}")
    return "\n".join(lines) if lines else "—"


def _receiver_messages(transfer: dict[str, Any], *, random_recipient: bool) -> list[str]:
    items_list = format_items_list(transfer.get("items", []), safe_int(transfer.get("coins"), 0))
    letter = str(transfer.get("letter") or "").strip()
    messages: list[str] = []
    if random_recipient:
        text = RANDOM_RECIPIENT_TEXT.format(items_list=items_list)
        if letter:
            text += RANDOM_RECIPIENT_LETTER_SUFFIX.format(letter_text=letter)
        messages.append(text)
        return messages
    messages.append(
        RECEIVER_COURIER_REPLY_TEXT.format(
            receiver_name=transfer.get("receiver_name", "игрок"),
            sender_name=transfer.get("sender_name", "игрок"),
        )
    )
    contents = RECEIVER_CONTENTS_TEXT.format(
        sender_name=transfer.get("sender_name", "игрок"),
        items_list=items_list,
    )
    if letter:
        contents += RECEIVER_LETTER_SUFFIX.format(letter_text=letter)
    messages.append(contents)
    return messages


# --- Создание посылки -------------------------------------------------------
def _item_key(item: dict[str, Any]) -> str:
    # Имя — запасной ключ: фронтенд (normalize_item) подставляет name в id, когда
    # у предмета нет id/item_id, поэтому без этого fallback'а легаси-стопки без id
    # было бы невозможно отправить (item_id с фронта != ключ на бэкенде).
    return str(item.get("id") or item.get("item_id") or item.get("name") or "").strip()


def _match_inventory_index(
    inventory: list[Any], item_id: str, inventory_index: int | None
) -> int | None:
    expected = str(item_id or "").strip()
    if inventory_index is not None:
        if 0 <= inventory_index < len(inventory):
            item = inventory[inventory_index]
            if isinstance(item, dict) and _item_key(item) == expected:
                return inventory_index
        return None
    for index, item in enumerate(inventory):
        if isinstance(item, dict) and _item_key(item) == expected:
            return index
    return None


def _queue_player_message(player: dict[str, Any], *messages: str) -> None:
    pending = player.setdefault("pending_bot_messages", [])
    if not isinstance(pending, list):
        pending = []
        player["pending_bot_messages"] = pending
    for message in messages:
        if message:
            pending.append(message)


def create_courier_transfer(
    storage: Any,
    sender: dict[str, Any],
    receiver_query: str,
    item_requests: list[dict[str, Any]],
    coins: int = 0,
    letter: str = "",
    *,
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Проверяет и оформляет посылку: списывает предметы/монеты/стоимость.

    Возвращает {"message": <подтверждение отправителю>, "transfer": <запись>}.
    Бросает CourierError с понятным текстом при ошибке валидации.
    """
    rng = rng or random.Random()
    now = now or _utc_now()

    coins = max(0, safe_int(coins, 0))
    letter = str(letter or "").strip()
    if len(letter) > LETTER_MAX_LENGTH:
        raise CourierError(f"Письмо не должно превышать {LETTER_MAX_LENGTH} символов.")

    receiver = find_player_by_query(storage, receiver_query)
    if receiver is None:
        raise CourierError("Игрок-получатель не найден. Проверьте ник или игровой ID.")

    sender_id = str(sender.get("game_id") or sender.get("id") or "")
    receiver_id = str(receiver.get("game_id") or receiver.get("id") or "")
    if receiver_id and receiver_id == sender_id:
        raise CourierError("Нельзя отправить посылку самому себе.")

    item_requests = list(item_requests or [])
    if not item_requests and coins <= 0:
        raise CourierError("Добавьте хотя бы один предмет или монеты.")

    level = safe_int(sender.get("level"), 1)
    cost = delivery_cost_copper(level)
    money = safe_int(sender.get("money"), 0)
    if money < cost + coins:
        raise CourierError("Недостаточно монет для оплаты доставки и вложенных монет.")

    inventory = sender.setdefault("inventory", [])
    if not isinstance(inventory, list):
        inventory = []
        sender["inventory"] = inventory

    # 1) Валидация всех предметов до любого списания (всё-или-ничего).
    planned: list[tuple[int, int, dict[str, Any]]] = []
    used_indexes: set[int] = set()
    for request in item_requests:
        item_id = str(request.get("item_id") or "").strip()
        inventory_index = request.get("inventory_index")
        if inventory_index is not None:
            inventory_index = safe_int(inventory_index, -1)
            if inventory_index < 0:
                inventory_index = None
        amount = max(1, safe_int(request.get("amount"), 1))
        index = _match_inventory_index(inventory, item_id, inventory_index)
        if index is None or index in used_indexes:
            raise CourierError("Предмет в инвентаре не найден. Обновите профиль и повторите.")
        item = inventory[index]
        available = max(1, safe_int(item.get("amount"), 1))
        if amount > available:
            raise CourierError(f"В стопке «{item.get('name', 'предмет')}» недостаточно предметов.")
        used_indexes.add(index)
        planned.append((index, amount, item))

    # 2) Снимок предметов и фактическое списание из инвентаря.
    items_snapshot: list[dict[str, Any]] = []
    for index, amount, item in planned:
        snapshot = deepcopy(item)
        snapshot.pop("inventoryIndex", None)
        items_snapshot.append({
            "item": snapshot,
            "amount": amount,
            "name": str(item.get("name") or "Предмет"),
            "item_id": _item_key(item),
        })
    # Списываем по убыванию индекса, чтобы не сместить ещё не обработанные.
    for index, amount, _item in sorted(planned, key=lambda row: row[0], reverse=True):
        current = max(1, safe_int(inventory[index].get("amount"), 1))
        if current > amount:
            inventory[index]["amount"] = current - amount
        else:
            inventory.pop(index)

    sender["money"] = money - cost - coins
    recalculate_inventory_overflow(sender)

    deliver_at = now + timedelta(
        minutes=rng.randint(DELIVERY_MIN_MINUTES, DELIVERY_MAX_MINUTES)
    )
    transfer = {
        "transfer_id": str(uuid.uuid4()),
        "sender_game_id": sender_id,
        "sender_name": str(sender.get("name") or "игрок"),
        "receiver_game_id": receiver_id,
        "receiver_name": str(receiver.get("name") or "игрок"),
        "items": items_snapshot,
        "coins": coins,
        "letter": letter,
        "delivery_cost": cost,
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "deliver_at": deliver_at.isoformat().replace("+00:00", "Z"),
    }

    # Сначала делаем списание у отправителя ДУРАБЛЬНЫМ, и только потом ставим
    # посылку в очередь. Иначе при сбое сохранения отправителя посылка всё равно
    # доставилась бы получателю → дублирование предметов/монет. При сбое самой
    # постановки в очередь откатываем списание, чтобы вложения не пропали.
    update_player = getattr(storage, "update_player", None)
    if callable(update_player):
        try:
            update_player(sender)
        except Exception as exc:  # списание не зафиксировано — ничего не теряем
            raise CourierError("Не удалось оформить посылку. Попробуйте позже.") from exc

    try:
        with _TRANSFERS_LOCK, _transfers_file_lock():
            queue = _load_transfers()
            queue.append(transfer)
            _save_transfers(queue)
    except Exception as exc:
        _refund_sender(sender, items_snapshot, cost, coins)
        if callable(update_player):
            try:
                update_player(sender)
            except Exception:
                pass
        raise CourierError("Не удалось оформить посылку. Попробуйте позже.") from exc

    message = SENDER_CONFIRM_TEXT.format(
        receiver_name=transfer["receiver_name"],
        delivery_cost=format_price(cost),
    )
    return {"message": message, "transfer": transfer}


def _refund_sender(
    sender: dict[str, Any], items_snapshot: list[dict[str, Any]], cost: int, coins: int
) -> None:
    """Возврат вложений и стоимости отправителю при сбое постановки в очередь."""
    for entry in items_snapshot:
        snapshot = entry.get("item")
        amount = max(1, safe_int(entry.get("amount"), 1))
        if isinstance(snapshot, dict):
            add_inventory_item(sender, deepcopy(snapshot), amount)
    sender["money"] = safe_int(sender.get("money"), 0) + safe_int(cost, 0) + safe_int(coins, 0)
    recalculate_inventory_overflow(sender)


# --- Доставка ---------------------------------------------------------------
def _claim_due_transfers(now: datetime) -> list[dict[str, Any]]:
    with _TRANSFERS_LOCK, _transfers_file_lock():
        queue = _load_transfers()
        if not queue:
            return []
        due: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        for transfer in queue:
            deliver_at = _parse_dt(transfer.get("deliver_at"))
            if deliver_at is not None and deliver_at <= now:
                due.append(transfer)
            else:
                pending.append(transfer)
        if due:
            _save_transfers(pending)
        return due


def _deliver_items_to(player: dict[str, Any], transfer: dict[str, Any]) -> None:
    for entry in transfer.get("items", []):
        snapshot = entry.get("item")
        amount = max(1, safe_int(entry.get("amount"), 1))
        if isinstance(snapshot, dict):
            add_inventory_item(player, deepcopy(snapshot), amount)
    coins = safe_int(transfer.get("coins"), 0)
    if coins > 0:
        player["money"] = safe_int(player.get("money"), 0) + coins
    recalculate_inventory_overflow(player)


def _pick_random_recipient(
    storage: Any, exclude_ids: set[str], rng: random.Random
) -> dict[str, Any] | None:
    candidates = [
        player
        for game_id, player in _all_players(storage).items()
        if game_id not in exclude_ids and not player.get("is_dead")
    ]
    return rng.choice(candidates) if candidates else None


def process_due_transfers(
    storage: Any,
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> int:
    """Тик доставки: разыгрывает исход для всех «созревших» посылок.

    Возвращает число обработанных посылок. Получатели/отправители
    перезагружаются перед изменением и сохраняются через update_player —
    фоновый тик не затирает свежие изменения игроков.
    """
    rng = rng or random.Random()
    now = now or _utc_now()
    due = _claim_due_transfers(now)
    if not due:
        return 0

    get_player = getattr(storage, "get_player_by_game_id", None)
    update_player = getattr(storage, "update_player", None)
    if not callable(update_player):
        return 0

    def _reload(game_id: str) -> dict[str, Any] | None:
        if game_id and callable(get_player):
            player = get_player(game_id)
            if isinstance(player, dict):
                return player
        return None

    processed = 0
    requeue: list[dict[str, Any]] = []
    for transfer in due:
        roll = rng.random() * 100.0
        sender_id = str(transfer.get("sender_game_id") or "")
        receiver_id = str(transfer.get("receiver_game_id") or "")
        try:
            if roll < STOLEN_CHANCE_PERCENT:
                sender = _reload(sender_id)
                if sender is not None:
                    _queue_player_message(
                        sender,
                        SENDER_STOLEN_TEXT.format(receiver_name=transfer.get("receiver_name", "игрок")),
                    )
                    update_player(sender)
            elif roll < STOLEN_CHANCE_PERCENT + MISDELIVERY_CHANCE_PERCENT:
                wrong = _pick_random_recipient(
                    storage, {sender_id, receiver_id}, rng
                )
                if wrong is not None:
                    _deliver_items_to(wrong, transfer)
                    _queue_player_message(wrong, *_receiver_messages(transfer, random_recipient=True))
                    update_player(wrong)
                sender = _reload(sender_id)
                if sender is not None:
                    _queue_player_message(
                        sender,
                        SENDER_MISDELIVERED_TEXT.format(receiver_name=transfer.get("receiver_name", "игрок")),
                    )
                    update_player(sender)
            else:
                receiver = _reload(receiver_id)
                if receiver is not None:
                    _deliver_items_to(receiver, transfer)
                    _queue_player_message(receiver, *_receiver_messages(transfer, random_recipient=False))
                    update_player(receiver)
            processed += 1
        except Exception:
            # Доставка не должна терять посылку: возвращаем её в очередь на
            # повтор (до MAX_DELIVERY_ATTEMPTS), иначе предметы/монеты отправителя
            # пропали бы навсегда при разовом сбое (например, ошибке БД).
            attempts = safe_int(transfer.get("delivery_attempts"), 0) + 1
            if attempts < MAX_DELIVERY_ATTEMPTS:
                transfer["delivery_attempts"] = attempts
                requeue.append(transfer)
            continue

    if requeue:
        with _TRANSFERS_LOCK, _transfers_file_lock():
            queue = _load_transfers()
            queue.extend(requeue)
            _save_transfers(queue)
    return processed


def start_persistent_courier_worker(
    storage: Any,
    *,
    interval_seconds: int | float = 60,
) -> threading.Event:
    """Постоянный фоновый воркер доставки посылок (как воркер эффектов)."""
    stop_event = threading.Event()
    interval = max(15.0, float(interval_seconds or 60))

    def loop() -> None:
        while not stop_event.wait(interval):
            try:
                process_due_transfers(storage)
            except Exception:
                pass

    thread = threading.Thread(
        target=loop,
        name="NerTalisCourierWorker",
        daemon=True,
    )
    thread.start()
    return stop_event
