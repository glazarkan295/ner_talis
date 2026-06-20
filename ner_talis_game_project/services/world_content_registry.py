"""Конструктор мира — генерик-реестр data-driven контента (ТЗ «Конструктор мира»).

Единый движок для локаций/мобов/событий/NPC/квестов и т.д. Каждый объект живёт
в едином жизненном цикле:

    draft → review → ready → published → disabled → archived
                                   ↘ error (после неуспешной проверки)

Движок — чистый слой данных: хранит объекты, гоняет валидацию и меняет статусы.
Аудит и проверку прав делает роутер (admin_world_api) через admin_operation —
так же, как для остальных мутаций V2. Хранилище — JSON-файл с блокировкой
(как admin_roles.json / порт-маркет), формат:

    { "<kind>": { "<id>": <envelope>, ... }, ... }

Envelope: id/kind/status/data/created_at/created_by/updated_at/updated_by/
version/validation.
"""

from __future__ import annotations

import json
import os
import re
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

try:  # POSIX-блокировка (на Windows отсутствует)
    import fcntl
except Exception:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

from project_paths import project_path, resolve_project_path

# --- Статусы жизненного цикла ----------------------------------------------
STATUS_DRAFT = "draft"
STATUS_REVIEW = "review"
STATUS_READY = "ready"
STATUS_PUBLISHED = "published"
STATUS_DISABLED = "disabled"
STATUS_ERROR = "error"
STATUS_ARCHIVED = "archived"

STATUSES = (
    STATUS_DRAFT, STATUS_REVIEW, STATUS_READY,
    STATUS_PUBLISHED, STATUS_DISABLED, STATUS_ERROR, STATUS_ARCHIVED,
)
STATUS_LABELS = {
    STATUS_DRAFT: "Черновик",
    STATUS_REVIEW: "На проверке",
    STATUS_READY: "Готово к публикации",
    STATUS_PUBLISHED: "Опубликовано",
    STATUS_DISABLED: "Отключено",
    STATUS_ERROR: "Ошибка проверки",
    STATUS_ARCHIVED: "Архив",
}

# Допустимые переходы статусов (защита от случайных скачков состояния).
STATUS_TRANSITIONS: dict[str, set[str]] = {
    STATUS_DRAFT: {STATUS_REVIEW, STATUS_READY, STATUS_ARCHIVED, STATUS_ERROR},
    STATUS_REVIEW: {STATUS_DRAFT, STATUS_READY, STATUS_ARCHIVED, STATUS_ERROR},
    STATUS_READY: {STATUS_DRAFT, STATUS_PUBLISHED, STATUS_ARCHIVED, STATUS_ERROR},
    STATUS_PUBLISHED: {STATUS_DISABLED, STATUS_ARCHIVED},
    STATUS_DISABLED: {STATUS_PUBLISHED, STATUS_DRAFT, STATUS_ARCHIVED},
    STATUS_ERROR: {STATUS_DRAFT, STATUS_REVIEW, STATUS_ARCHIVED},
    STATUS_ARCHIVED: set(),
}

# --- Поддерживаемые типы контента ------------------------------------------
KIND_LOCATION = "location"
KIND_MOB = "mob"
KIND_BUTTON = "button"
KIND_TRANSITION = "transition"
KIND_EVENT = "event"
KIND_NPC = "npc"
KIND_QUEST = "quest"
KIND_RAID = "raid"
KINDS = (
    KIND_LOCATION, KIND_MOB, KIND_BUTTON, KIND_TRANSITION,
    KIND_EVENT, KIND_NPC, KIND_QUEST, KIND_RAID,
)

LOCATION_TYPES = (
    "city", "starting", "wild", "dungeon", "fortress", "raid",
    "world_boss", "port", "market", "camp", "story", "event",
)
# Локации, для которых тупик (нет выходов) — норма (сюжет/событие/лагерь).
_DEAD_END_OK_TYPES = {"story", "event", "camp"}

BUTTON_ACTIONS = (
    "goto_location", "show_message", "start_search", "start_battle",
    "open_shop", "open_npc", "open_quests", "open_raids", "give_item",
    "take_item", "check_condition", "start_event", "open_fishing",
    "open_camp", "go_back",
)
# Действия кнопки, которые считаются «выходом» из локации (против тупика).
_EXIT_BUTTON_ACTIONS = {"goto_location", "go_back"}

ACCESS_CONDITIONS = (
    "always", "from_level", "need_item", "need_quest", "need_reputation",
    "blocked_fine", "blocked_mute_ban", "blocked_battle", "blocked_timer",
    "blocked_event",
)

EVENT_TYPES = (
    "found_resource", "found_item", "met_mob", "trap", "chest", "npc",
    "story", "curse", "raid", "energy_loss", "buff", "debuff",
    "hidden_transition", "rare_find",
)
EVENT_RESULT_TYPES = (
    "give_item", "give_currency", "give_exp", "take_item", "take_currency",
    "take_energy", "start_battle", "move_player", "apply_buff", "apply_debuff",
    "show_text", "open_buttons", "start_timer", "give_fine", "start_raid",
)
NPC_FUNCTIONS = (
    "shop", "dialog", "give_quest", "accept_quest", "repair", "pay_fines",
    "raids", "board", "craft", "teleport", "trade", "training", "informant",
)
QUEST_GOAL_TYPES = (
    "bring_item", "kill_mob", "find_resource", "visit_location",
    "talk_npc", "deliver_item", "activate_object",
)
RAID_TYPES = ("world_boss", "dungeon", "expedition", "event_raid")

MOB_TYPES = (
    "beast", "undead", "bandit", "monster", "magic",
    "human", "boss", "world_boss", "event", "raid",
)

# Экономические «потолки» награды за одного моба — превышение даёт warning
# (не блок), чтобы конструктор не плодил инфляцию незаметно.
MAX_MOB_EXPERIENCE = 1_000_000
MAX_MOB_COINS = 1_000_000
# Валюта-синтетика из админ-наград допустима и в дропе.
_CURRENCY_ITEM_IDS = {"money_copper", "money_silver", "money_gold"}

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{1,63}$")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


class ContentError(ValueError):
    """Ошибка операции реестра (не найдено / дубликат / запрещённый переход)."""


# --- Хранилище (файл с блокировкой) ----------------------------------------
_STORE_LOCK = threading.Lock()


def content_path() -> Path:
    override = os.getenv("WORLD_CONTENT_PATH")
    if override:
        return resolve_project_path(override)
    return project_path("data", "world_content.json")


def _load_all() -> dict[str, dict[str, Any]]:
    path = content_path()
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_all(data: dict[str, dict[str, Any]]) -> None:
    path = content_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


@contextmanager
def _store_file_lock() -> Iterator[None]:
    if fcntl is None:
        yield
        return
    path = content_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_kind(kind: str) -> str:
    if kind not in KINDS:
        raise ContentError(f"Неизвестный тип контента: {kind}.")
    return kind


# --- Чтение ----------------------------------------------------------------
def list_content(kind: str, *, status: str | None = None) -> list[dict[str, Any]]:
    _ensure_kind(kind)
    with _STORE_LOCK, _store_file_lock():
        bucket = _load_all().get(kind, {})
    items = [v for v in bucket.values() if isinstance(v, dict)]
    if status:
        items = [v for v in items if v.get("status") == status]
    items.sort(key=lambda v: str(v.get("updated_at") or ""), reverse=True)
    return items


def get_content(kind: str, content_id: str) -> dict[str, Any] | None:
    _ensure_kind(kind)
    with _STORE_LOCK, _store_file_lock():
        bucket = _load_all().get(kind, {})
    obj = bucket.get(str(content_id))
    return obj if isinstance(obj, dict) else None


# --- Мутации ---------------------------------------------------------------
def create_content(kind: str, content_id: str, data: dict[str, Any], *, actor: str = "") -> dict[str, Any]:
    _ensure_kind(kind)
    content_id = str(content_id or "").strip()
    if not _ID_RE.match(content_id):
        raise ContentError(
            "ID должен быть из латиницы/цифр/подчёркиваний (2–64 символа), "
            "начинаться с буквы или цифры."
        )
    with _STORE_LOCK, _store_file_lock():
        store = _load_all()
        bucket = store.setdefault(kind, {})
        if content_id in bucket:
            raise ContentError(f"Объект {kind}:{content_id} уже существует.")
        now = _now_iso()
        envelope = {
            "id": content_id,
            "kind": kind,
            "status": STATUS_DRAFT,
            "data": data if isinstance(data, dict) else {},
            "created_at": now,
            "created_by": str(actor or ""),
            "updated_at": now,
            "updated_by": str(actor or ""),
            "version": 1,
            "validation": None,
        }
        bucket[content_id] = envelope
        _save_all(store)
        return dict(envelope)


def update_content(kind: str, content_id: str, data: dict[str, Any], *, actor: str = "") -> dict[str, Any]:
    _ensure_kind(kind)
    content_id = str(content_id)
    with _STORE_LOCK, _store_file_lock():
        store = _load_all()
        bucket = store.get(kind, {})
        envelope = bucket.get(content_id)
        if not isinstance(envelope, dict):
            raise ContentError(f"Объект {kind}:{content_id} не найден.")
        if envelope.get("status") == STATUS_ARCHIVED:
            raise ContentError("Архивный объект редактировать нельзя.")
        merged = dict(envelope.get("data") or {})
        merged.update(data if isinstance(data, dict) else {})
        envelope["data"] = merged
        envelope["updated_at"] = _now_iso()
        envelope["updated_by"] = str(actor or "")
        envelope["version"] = int(envelope.get("version") or 1) + 1
        # Любая правка обнуляет прошлую валидацию (надо проверить заново).
        envelope["validation"] = None
        # Опубликованный объект после правки уходит в черновик (правится копия).
        if envelope.get("status") == STATUS_PUBLISHED:
            envelope["status"] = STATUS_DRAFT
        bucket[content_id] = envelope
        _save_all(store)
        return dict(envelope)


def set_status(kind: str, content_id: str, status: str, *, actor: str = "", force: bool = False) -> dict[str, Any]:
    _ensure_kind(kind)
    if status not in STATUSES:
        raise ContentError(f"Неизвестный статус: {status}.")
    content_id = str(content_id)
    with _STORE_LOCK, _store_file_lock():
        store = _load_all()
        bucket = store.get(kind, {})
        envelope = bucket.get(content_id)
        if not isinstance(envelope, dict):
            raise ContentError(f"Объект {kind}:{content_id} не найден.")
        current = str(envelope.get("status") or STATUS_DRAFT)
        if not force and status != current and status not in STATUS_TRANSITIONS.get(current, set()):
            raise ContentError(
                f"Недопустимый переход статуса: {STATUS_LABELS.get(current, current)} → "
                f"{STATUS_LABELS.get(status, status)}."
            )
        envelope["status"] = status
        envelope["updated_at"] = _now_iso()
        envelope["updated_by"] = str(actor or "")
        bucket[content_id] = envelope
        _save_all(store)
        return dict(envelope)


def record_validation(kind: str, content_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """Сохранить результат валидации в envelope (без смены статуса)."""
    _ensure_kind(kind)
    content_id = str(content_id)
    with _STORE_LOCK, _store_file_lock():
        store = _load_all()
        bucket = store.get(kind, {})
        envelope = bucket.get(content_id)
        if not isinstance(envelope, dict):
            raise ContentError(f"Объект {kind}:{content_id} не найден.")
        envelope["validation"] = {**result, "checked_at": _now_iso()}
        bucket[content_id] = envelope
        _save_all(store)
        return dict(envelope)


# --- Валидация -------------------------------------------------------------
def _str_field(data: dict[str, Any], key: str) -> str:
    return str(data.get(key) or "").strip()


def _has_markup(value: str) -> bool:
    low = value.lower()
    return "<script" in low or bool(_HTML_TAG_RE.search(value))


def _validate_location(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Проверка локации (ТЗ §14, применимая часть). Возвращает (errors, warnings)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    name = _str_field(data, "name")
    if not name:
        errors.append("Не заполнено название локации.")
    short = _str_field(data, "short_description")
    full = _str_field(data, "description")
    if not short and not full:
        errors.append("Нужно хотя бы краткое описание локации.")

    loc_type = _str_field(data, "type")
    if loc_type and loc_type not in LOCATION_TYPES:
        errors.append(f"Неизвестный тип локации: {loc_type}.")

    # Уровни.
    min_level = data.get("min_level")
    if min_level is not None:
        try:
            if int(min_level) < 1:
                errors.append("Минимальный уровень должен быть ≥ 1.")
        except (TypeError, ValueError):
            errors.append("Минимальный уровень — не число.")
    mob_min = data.get("mob_level_min")
    mob_max = data.get("mob_level_max")
    if mob_min is not None and mob_max is not None:
        try:
            if int(mob_min) > int(mob_max):
                errors.append("Минимальный уровень мобов больше максимального.")
        except (TypeError, ValueError):
            errors.append("Уровни мобов — не числа.")

    # Безопасность текстов: никакого HTML/скриптов.
    for key in ("name", "short_description", "description"):
        value = _str_field(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")

    if not loc_type:
        warnings.append("Не указан тип локации.")

    # Тупиковая локация (нет выходов) — норма только для сюжет/событие/лагерь.
    loc_id = str(envelope.get("id") or "")
    if loc_id and loc_type not in _DEAD_END_OK_TYPES:
        try:
            if not location_has_exit(loc_id):
                warnings.append("Локация выглядит тупиковой: нет переходов или кнопок выхода.")
        except Exception:
            pass

    return errors, warnings


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _item_exists(item_id: str) -> bool:
    iid = str(item_id or "").strip()
    if not iid:
        return False
    if iid in _CURRENCY_ITEM_IDS:
        return True
    try:  # ленивый импорт, чтобы движок оставался автономным
        from services.item_registry import get_item_definition_by_id

        return get_item_definition_by_id(iid) is not None
    except Exception:  # реестр недоступен — не валим проверку
        return True


def _validate_drop_rows(rows: Any, errors: list[str], warnings: list[str]) -> None:
    """Проверка таблицы дропа моба (ТЗ §7)."""
    if rows in (None, ""):
        return
    if not isinstance(rows, list):
        errors.append("Дроп должен быть списком строк.")
        return
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"Дроп строка {index}: неверный формат.")
            continue
        item_id = str(row.get("item_id") or "").strip()
        if not item_id:
            errors.append(f"Дроп строка {index}: не указан предмет.")
        elif not _item_exists(item_id):
            errors.append(f"Дроп строка {index}: предмет «{item_id}» не существует.")
        chance = _num(row.get("chance"))
        if chance is None:
            errors.append(f"Дроп строка {index}: шанс не число.")
        elif chance < 0 or chance > 100:
            errors.append(f"Дроп строка {index}: шанс должен быть 0–100.")
        cmin = _num(row.get("min_count"))
        cmax = _num(row.get("max_count"))
        if cmin is not None and cmin < 0:
            errors.append(f"Дроп строка {index}: количество не может быть отрицательным.")
        if cmin is not None and cmax is not None and cmin > cmax:
            errors.append(f"Дроп строка {index}: мин. количество больше макс.")


def _validate_mob(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Проверка моба и его дропа (ТЗ §6–7)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not _str_field(data, "name"):
        errors.append("Не заполнено название моба.")
    mob_type = _str_field(data, "type")
    if mob_type and mob_type not in MOB_TYPES:
        errors.append(f"Неизвестный тип моба: {mob_type}.")

    min_level = _num(data.get("min_level"))
    max_level = _num(data.get("max_level"))
    if min_level is not None and min_level < 1:
        errors.append("Минимальный уровень должен быть ≥ 1.")
    if min_level is not None and max_level is not None and min_level > max_level:
        errors.append("Минимальный уровень моба больше максимального.")

    hp = _num(data.get("hp"))
    if hp is None or hp <= 0:
        errors.append("HP моба должно быть положительным.")

    # Боевые/числовые поля не должны быть отрицательными.
    numeric_fields = (
        "phys_damage", "mag_damage", "accuracy", "evasion",
        "phys_defense", "mag_defense", "crit_chance", "crit_damage",
        "experience", "coins", "spawn_chance",
    )
    for key in numeric_fields:
        if data.get(key) in (None, ""):
            continue
        value = _num(data.get(key))
        if value is None:
            errors.append(f"Поле «{key}» — не число.")
        elif value < 0:
            errors.append(f"Поле «{key}» не может быть отрицательным.")

    chance = _num(data.get("spawn_chance"))
    if chance is not None and chance > 100:
        errors.append("Шанс появления должен быть ≤ 100.")

    # Экономические пороги — предупреждения.
    exp = _num(data.get("experience"))
    if exp is not None and exp > MAX_MOB_EXPERIENCE:
        warnings.append("Очень большой опыт за моба — проверьте баланс.")
    coins = _num(data.get("coins"))
    if coins is not None and coins > MAX_MOB_COINS:
        warnings.append("Очень много валюты за моба — проверьте экономику.")

    for key in ("name", "description"):
        value = _str_field(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")

    _validate_drop_rows(data.get("drop"), errors, warnings)

    if not mob_type:
        warnings.append("Не указан тип моба.")
    return errors, warnings


def _location_exists(loc_id: Any) -> bool:
    loc_id = str(loc_id or "").strip()
    if not loc_id:
        return False
    return get_content(KIND_LOCATION, loc_id) is not None


def location_has_exit(loc_id: str) -> bool:
    """Есть ли у локации выход — переход наружу или кнопка goto/go_back."""
    loc_id = str(loc_id or "").strip()
    if not loc_id:
        return False
    for t in list_content(KIND_TRANSITION):
        if str((t.get("data") or {}).get("from_location") or "") == loc_id:
            return True
    for b in list_content(KIND_BUTTON):
        data = b.get("data") or {}
        if str(data.get("owner_location") or "") == loc_id and data.get("action") in _EXIT_BUTTON_ACTIONS:
            return True
    return False


def _validate_button(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Проверка кнопки локации (ТЗ §4)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    text = _str_field(data, "text")
    if not text:
        errors.append("Не заполнен текст кнопки.")
    elif _has_markup(text):
        errors.append("В тексте кнопки недопустимая разметка/HTML.")

    owner = _str_field(data, "owner_location")
    if not owner:
        errors.append("Не указана локация-владелец кнопки.")
    elif not _location_exists(owner):
        errors.append(f"Локация-владелец «{owner}» не существует.")

    action = _str_field(data, "action")
    if not action:
        errors.append("Не выбрано действие кнопки.")
    elif action not in BUTTON_ACTIONS:
        errors.append(f"Неизвестное действие кнопки: {action}.")

    target = _str_field(data, "target")
    if action == "goto_location":
        if not target:
            errors.append("Для перехода укажите целевую локацию.")
        elif not _location_exists(target):
            errors.append(f"Целевая локация «{target}» не существует.")

    order = data.get("order")
    if order not in (None, "") and _num(order) is None:
        warnings.append("Порядок отображения — не число.")
    if not data.get("show_telegram") and not data.get("show_vk"):
        warnings.append("Кнопка скрыта и в Telegram, и в VK.")

    return errors, warnings


def _validate_transition(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Проверка перехода между локациями (ТЗ §5)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    frm = _str_field(data, "from_location")
    to = _str_field(data, "to_location")
    if not frm:
        errors.append("Не указана локация-источник.")
    elif not _location_exists(frm):
        errors.append(f"Локация-источник «{frm}» не существует.")
    if not to:
        errors.append("Не указана целевая локация.")
    elif not _location_exists(to):
        errors.append(f"Целевая локация «{to}» не существует.")
    if frm and to and frm == to:
        errors.append("Переход ведёт в ту же локацию.")

    cond = _str_field(data, "access_condition")
    if cond and cond not in ACCESS_CONDITIONS:
        errors.append(f"Неизвестное условие доступа: {cond}.")

    cost = data.get("cost")
    if cost not in (None, ""):
        c = _num(cost)
        if c is None:
            errors.append("Стоимость перехода — не число.")
        elif c < 0:
            errors.append("Стоимость перехода не может быть отрицательной.")

    name = _str_field(data, "name")
    if name and _has_markup(name):
        errors.append("В названии перехода недопустимая разметка/HTML.")

    return errors, warnings


def _mob_exists(mob_id: Any) -> bool:
    mob_id = str(mob_id or "").strip()
    return bool(mob_id) and get_content(KIND_MOB, mob_id) is not None


def _npc_exists(npc_id: Any) -> bool:
    npc_id = str(npc_id or "").strip()
    return bool(npc_id) and get_content(KIND_NPC, npc_id) is not None


def _check_item_ref(data: dict[str, Any], key: str, label: str, errors: list[str]) -> None:
    item_id = _str_field(data, key)
    if item_id and not _item_exists(item_id):
        errors.append(f"{label} «{item_id}» не существует в каталоге.")


def _validate_event(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Проверка события поиска (ТЗ §8)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not _str_field(data, "name"):
        errors.append("Не заполнено название события.")
    if not _str_field(data, "text"):
        errors.append("Не заполнен текст события для игрока.")

    location = _str_field(data, "location")
    if not location:
        errors.append("Не указана локация события.")
    elif not _location_exists(location):
        errors.append(f"Локация «{location}» не существует.")

    ev_type = _str_field(data, "type")
    if ev_type and ev_type not in EVENT_TYPES:
        errors.append(f"Неизвестный тип события: {ev_type}.")
    result = _str_field(data, "result")
    if result and result not in EVENT_RESULT_TYPES:
        errors.append(f"Неизвестный результат события: {result}.")

    chance = _num(data.get("chance"))
    if chance is not None and (chance < 0 or chance > 100):
        errors.append("Шанс события должен быть 0–100.")
    cooldown = _num(data.get("cooldown"))
    if cooldown is not None and cooldown < 0:
        errors.append("Кулдаун не может быть отрицательным.")

    min_level = _num(data.get("min_level"))
    max_level = _num(data.get("max_level"))
    if min_level is not None and max_level is not None and min_level > max_level:
        errors.append("Минимальный уровень события больше максимального.")

    _check_item_ref(data, "required_item", "Требуемый предмет", errors)
    _check_item_ref(data, "consumed_item", "Списываемый предмет", errors)
    _check_item_ref(data, "given_item", "Выдаваемый предмет", errors)

    battle_mob = _str_field(data, "battle_mob")
    if battle_mob and not _mob_exists(battle_mob):
        errors.append(f"Запускаемый моб «{battle_mob}» не существует.")

    for key in ("name", "text"):
        value = _str_field(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")
    return errors, warnings


def _validate_npc(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Проверка NPC (ТЗ §9)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not _str_field(data, "name"):
        errors.append("Не заполнено имя NPC.")

    location = _str_field(data, "location")
    if location and not _location_exists(location):
        errors.append(f"Локация «{location}» не существует.")
    elif not location:
        warnings.append("Не указана локация NPC.")

    functions = data.get("functions")
    if functions not in (None, ""):
        if not isinstance(functions, list):
            errors.append("Функции NPC должны быть списком.")
        else:
            for fn in functions:
                if fn not in NPC_FUNCTIONS:
                    errors.append(f"Неизвестная функция NPC: {fn}.")

    for key in ("name", "description", "first_message"):
        value = _str_field(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")
    return errors, warnings


def _validate_quest(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Проверка простого квеста/поручения (ТЗ §10)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not _str_field(data, "name"):
        errors.append("Не заполнено название задания.")

    goal_type = _str_field(data, "goal_type")
    if goal_type and goal_type not in QUEST_GOAL_TYPES:
        errors.append(f"Неизвестная цель задания: {goal_type}.")
    target = _str_field(data, "goal_target")
    if goal_type and not target:
        errors.append("Не указана цель задания (предмет/моб/локация/NPC).")
    elif target:
        if goal_type in ("bring_item", "deliver_item") and not _item_exists(target):
            errors.append(f"Цель-предмет «{target}» не существует в каталоге.")
        elif goal_type == "kill_mob" and not _mob_exists(target):
            errors.append(f"Цель-моб «{target}» не существует.")
        elif goal_type == "visit_location" and not _location_exists(target):
            errors.append(f"Цель-локация «{target}» не существует.")
        elif goal_type == "talk_npc" and not _npc_exists(target):
            errors.append(f"Цель-NPC «{target}» не существует.")

    npc_giver = _str_field(data, "npc_giver")
    if npc_giver and not _npc_exists(npc_giver):
        errors.append(f"NPC-выдаватель «{npc_giver}» не существует.")
    location = _str_field(data, "location")
    if location and not _location_exists(location):
        errors.append(f"Локация «{location}» не существует.")

    cooldown = _num(data.get("cooldown"))
    if cooldown is not None and cooldown < 0:
        errors.append("Кулдаун не может быть отрицательным.")

    for key in ("name", "description"):
        value = _str_field(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")
    return errors, warnings


def _validate_raid(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Проверка рейдовой точки (ТЗ §11)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not _str_field(data, "name"):
        errors.append("Не заполнено название рейда.")

    entry = _str_field(data, "entry_location")
    if not entry:
        errors.append("Не указана локация входа в рейд.")
    elif not _location_exists(entry):
        errors.append(f"Локация входа «{entry}» не существует.")

    raid_type = _str_field(data, "raid_type")
    if raid_type and raid_type not in RAID_TYPES:
        errors.append(f"Неизвестный тип рейда: {raid_type}.")

    boss = _str_field(data, "boss_mob")
    if boss and not _mob_exists(boss):
        errors.append(f"Босс «{boss}» не существует среди мобов.")

    min_level = _num(data.get("min_level"))
    if min_level is not None and min_level < 1:
        errors.append("Минимальный уровень должен быть ≥ 1.")
    max_members = _num(data.get("max_members"))
    if max_members is not None and max_members < 1:
        errors.append("Максимум участников должен быть ≥ 1.")
    elif max_members is None:
        warnings.append("Не указан максимум участников.")
    cooldown = _num(data.get("cooldown"))
    if cooldown is not None and cooldown < 0:
        errors.append("Кулдаун не может быть отрицательным.")

    for key in ("name", "description"):
        value = _str_field(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")
    return errors, warnings


VALIDATORS: dict[str, Callable[[dict[str, Any]], tuple[list[str], list[str]]]] = {
    KIND_LOCATION: _validate_location,
    KIND_MOB: _validate_mob,
    KIND_BUTTON: _validate_button,
    KIND_TRANSITION: _validate_transition,
    KIND_EVENT: _validate_event,
    KIND_NPC: _validate_npc,
    KIND_QUEST: _validate_quest,
    KIND_RAID: _validate_raid,
}


def validate_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    kind = str(envelope.get("kind") or "")
    validator = VALIDATORS.get(kind)
    if validator is None:
        return {"ok": True, "errors": [], "warnings": []}
    errors, warnings = validator(envelope)
    return {"ok": not errors, "errors": errors, "warnings": warnings}


# --- Предпросмотр и тестовый проход (ТЗ §12) -------------------------------
def _spawns_in_location(mob_data: dict[str, Any], loc_id: str) -> bool:
    raw = mob_data.get("locations")
    if isinstance(raw, list):
        ids = [str(x).strip() for x in raw]
    else:
        ids = [p.strip() for p in str(raw or "").split(",")]
    return loc_id in [i for i in ids if i]


def _related_to_location(loc_id: str) -> dict[str, list[dict[str, Any]]]:
    """Собрать связанные с локацией объекты для предпросмотра/теста."""
    buttons = [b for b in list_content(KIND_BUTTON)
               if str((b.get("data") or {}).get("owner_location") or "") == loc_id]
    buttons.sort(key=lambda b: _num((b.get("data") or {}).get("order")) or 0)
    return {
        "buttons": buttons,
        "transitions": [t for t in list_content(KIND_TRANSITION)
                        if str((t.get("data") or {}).get("from_location") or "") == loc_id],
        "events": [e for e in list_content(KIND_EVENT)
                   if str((e.get("data") or {}).get("location") or "") == loc_id],
        "npcs": [n for n in list_content(KIND_NPC)
                 if str((n.get("data") or {}).get("location") or "") == loc_id],
        "mobs": [m for m in list_content(KIND_MOB)
                 if _spawns_in_location(m.get("data") or {}, loc_id)],
    }


def build_preview(kind: str, content_id: str) -> dict[str, Any] | None:
    """Как объект увидит игрок. Для локации — полная сцена с кнопками/событиями."""
    envelope = get_content(kind, content_id)
    if envelope is None:
        return None
    data = envelope.get("data") or {}
    if kind != KIND_LOCATION:
        return {
            "kind": kind, "id": content_id,
            "title": data.get("name") or data.get("text") or content_id,
            "text": data.get("description") or data.get("text") or "",
            "status": envelope.get("status"),
        }

    related = _related_to_location(content_id)

    def _btn_view(b):
        d = b.get("data") or {}
        return {
            "text": d.get("text"), "action": d.get("action"), "target": d.get("target"),
            "telegram": bool(d.get("show_telegram")), "vk": bool(d.get("show_vk")),
            "status": b.get("status"),
        }

    visible = [b for b in related["buttons"] if b.get("status") != STATUS_ARCHIVED]
    return {
        "kind": kind, "id": content_id,
        "title": data.get("name") or content_id,
        "text": data.get("description") or data.get("short_description") or "",
        "status": envelope.get("status"),
        "telegramButtons": [(b.get("data") or {}).get("text") for b in visible if (b.get("data") or {}).get("show_telegram")],
        "vkButtons": [(b.get("data") or {}).get("text") for b in visible if (b.get("data") or {}).get("show_vk")],
        "buttons": [_btn_view(b) for b in related["buttons"]],
        "transitions": [{
            "to": (t.get("data") or {}).get("to_location"),
            "name": (t.get("data") or {}).get("name"),
            "access": (t.get("data") or {}).get("access_condition"),
            "status": t.get("status"),
        } for t in related["transitions"]],
        "events": [{
            "name": (e.get("data") or {}).get("name"),
            "type": (e.get("data") or {}).get("type"),
            "chance": (e.get("data") or {}).get("chance"),
            "result": (e.get("data") or {}).get("result"),
            "status": e.get("status"),
        } for e in related["events"]],
        "npcs": [{
            "name": (n.get("data") or {}).get("name"),
            "role": (n.get("data") or {}).get("role"),
            "functions": (n.get("data") or {}).get("functions"),
            "status": n.get("status"),
        } for n in related["npcs"]],
        "mobs": [{
            "name": (m.get("data") or {}).get("name"),
            "type": (m.get("data") or {}).get("type"),
            "status": m.get("status"),
        } for m in related["mobs"]],
    }


def test_run(kind: str, content_id: str) -> dict[str, Any] | None:
    """Тестовый проход: валидация объекта и (для локации) всего его подграфа.

    Это безопасная сухая проверка связей перед публикацией — она не трогает
    живую игру и тестовый профиль, а собирает проблемы по объекту и всем
    связанным с ним кнопкам/переходам/событиям/NPC/мобам.
    """
    envelope = get_content(kind, content_id)
    if envelope is None:
        return None

    checks: list[dict[str, Any]] = []

    def _add(env: dict[str, Any]) -> None:
        result = validate_envelope(env)
        data = env.get("data") or {}
        checks.append({
            "kind": env.get("kind"),
            "id": env.get("id"),
            "title": data.get("name") or data.get("text") or env.get("id"),
            "status": env.get("status"),
            "ok": result["ok"],
            "errors": result["errors"],
            "warnings": result["warnings"],
        })

    _add(envelope)
    if kind == KIND_LOCATION:
        related = _related_to_location(content_id)
        for group in ("buttons", "transitions", "events", "npcs"):
            for env in related[group]:
                _add(env)

    return {
        "ok": all(c["ok"] for c in checks),
        "checks": checks,
        "preview": build_preview(kind, content_id),
    }
