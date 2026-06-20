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
# По мере роста сюда добавляются button/transition/loot/event/npc/quest/raid.
KINDS = (KIND_LOCATION, KIND_MOB)

LOCATION_TYPES = (
    "city", "starting", "wild", "dungeon", "fortress", "raid",
    "world_boss", "port", "market", "camp", "story", "event",
)

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

    # Предупреждение про тупиковую локацию (переходы появятся позже).
    if not loc_type:
        warnings.append("Не указан тип локации.")

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


VALIDATORS: dict[str, Callable[[dict[str, Any]], tuple[list[str], list[str]]]] = {
    KIND_LOCATION: _validate_location,
    KIND_MOB: _validate_mob,
}


def validate_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    kind = str(envelope.get("kind") or "")
    validator = VALIDATORS.get(kind)
    if validator is None:
        return {"ok": True, "errors": [], "warnings": []}
    errors, warnings = validator(envelope)
    return {"ok": not errors, "errors": errors, "warnings": warnings}
