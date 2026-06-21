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
# Расширенный конструктор локаций (ТЗ «Конструктор локаций»): под-объекты
# локации живут в том же генерик-движке (один envelope/жизненный цикл).
KIND_LOCATION_ZONE = "location_zone"
KIND_LOCATION_RESOURCE = "location_resource"
KIND_LOCATION_LOOT = "location_loot"
KIND_LOCATION_MOB_SPAWN = "location_mob_spawn"
KIND_LOCATION_WEEKLY_LIMIT = "location_weekly_limit"
KIND_LOCATION_WEEKLY_ROTATION = "location_weekly_rotation"
KIND_LOCATION_DEPLETION_RULE = "location_depletion_rule"
KIND_LOCATION_EMPTY_EVENT = "location_empty_event"
KIND_LOCATION_HIDDEN_EVENT = "location_hidden_event"
KIND_LOCATION_EVENT_ANSWER = "location_event_answer"
# Расширенный конструктор мобов (ТЗ «Конструктор мобов»): под-объекты моба в том
# же генерик-движке. Связь моб↔локация ведётся через KIND_LOCATION_MOB_SPAWN
# (тот же объект с двух сторон), отдельного mob_location_link нет — без дублей.
KIND_MOB_VARIANT = "mob_variant"
KIND_MOB_SKILL = "mob_skill"
KIND_MOB_PASSIVE = "mob_passive"
KIND_MOB_RESISTANCE = "mob_resistance"
KIND_MOB_EFFECT = "mob_effect"
KIND_MOB_EVENT_LINK = "mob_event_link"
KIND_MOB_ZONE_LINK = "mob_zone_link"
KIND_MOB_PHASE = "mob_phase"
KINDS = (
    KIND_LOCATION, KIND_MOB, KIND_BUTTON, KIND_TRANSITION,
    KIND_EVENT, KIND_NPC, KIND_QUEST, KIND_RAID,
    KIND_LOCATION_ZONE, KIND_LOCATION_RESOURCE, KIND_LOCATION_LOOT,
    KIND_LOCATION_MOB_SPAWN, KIND_LOCATION_WEEKLY_LIMIT,
    KIND_LOCATION_WEEKLY_ROTATION, KIND_LOCATION_DEPLETION_RULE,
    KIND_LOCATION_EMPTY_EVENT, KIND_LOCATION_HIDDEN_EVENT,
    KIND_LOCATION_EVENT_ANSWER,
    KIND_MOB_VARIANT, KIND_MOB_SKILL, KIND_MOB_PASSIVE, KIND_MOB_RESISTANCE,
    KIND_MOB_EFFECT, KIND_MOB_EVENT_LINK, KIND_MOB_ZONE_LINK, KIND_MOB_PHASE,
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

MOB_TYPES = (  # ТЗ §5 (расширено)
    "beast", "undead", "bandit", "monster", "magic",
    "human", "boss", "world_boss", "event", "raid",
    "dwarf", "elf", "lizardfolk", "spirit", "demon", "cursed",
    "mechanism", "golem", "elemental", "elite_boss", "holiday", "guild",
)

# --- Справочники расширенного конструктора мобов ---------------------------
MOB_VARIANT_TYPES = (  # ТЗ §6.1
    "normal", "enhanced", "elite", "rare", "dangerous", "mini_boss",
    "boss", "raid", "world_boss", "event", "holiday", "cursed", "zonal",
)
MOB_ATTACK_TYPES = (  # ТЗ §8
    "physical", "magical", "mixed", "poison", "bleed", "fire", "frost",
    "water", "earth", "wind", "spirit", "curse", "pure",
)
MOB_SKILL_TYPES = (  # ТЗ §9.2
    "basic_attack", "heavy_attack", "magic_attack", "aoe_attack", "poison",
    "bleed", "stun", "burn", "curse", "weaken", "reduce_accuracy",
    "reduce_evasion", "reduce_defense", "self_heal", "regen", "summon",
    "self_buff", "defensive_stance", "counter", "vampirism", "flee", "boss_phase",
)
MOB_SKILL_CONDITIONS = (  # ТЗ §9.3
    "always", "hp_below", "player_uses_magic", "player_uses_physical",
    "after_n_turns", "mob_enhanced", "mob_elite", "zone_active",
    "world_event_active", "raid_battle", "has_allies", "player_has_effect",
)
MOB_BEHAVIOR_TYPES = (  # ТЗ §25.1
    "aggressive", "cautious", "defensive", "fast", "magical", "poisonous",
    "summoner", "support", "boss_phases", "random",
)
MOB_RESIST_TYPES = (  # ТЗ §11.1
    "physical", "magical", "fire", "water", "frost", "earth", "wind",
    "spirit", "poison", "bleed", "stun", "curse", "periodic", "crit",
)

# --- Справочники расширенного конструктора локаций -------------------------
ZONE_TYPES = (  # ТЗ §43.1
    "fire", "water", "frost", "earth", "wind", "spirit", "cursed",
    "poison", "dark", "light", "magic_anomaly", "raid_zone",
    "high_loot", "high_danger",
)
RESOURCE_CATEGORIES = (  # ТЗ §13.2
    "herb", "berry", "alchemy", "wood", "stone", "ore", "leather",
    "bone", "fish", "shellfish", "pearl", "trophy", "event", "guild", "rare",
)
LOOT_SOURCES = (  # ТЗ §14.2 / §21
    "search", "gather", "fishing", "chest", "event", "hidden_event",
    "battle", "mob_drop", "npc", "quest", "raid", "world_event", "guild_event",
)
WEEKLY_LIMIT_TYPES = (  # ТЗ §20
    "resource", "item", "trophy", "mob", "mob_group", "rare_mob", "boss",
    "event", "hidden_event", "mob_drop", "event_currency", "event_item",
    "guild_resource", "world_progress",
)
ROTATION_PERIODICITY = ("weekly", "biweekly", "monthly", "event", "manual")  # §36.2
ROTATION_SELECTION_MODES = (  # ТЗ §37
    "random", "weighted_random", "fixed_calendar", "seasonal",
    "manual", "by_world_event", "by_holiday", "by_economy",
)
REDISTRIBUTION_MODES = (  # ТЗ §29
    "even", "by_weight", "same_group", "normal_only", "same_category", "none",
)
EVENT_GROUPS = (  # ТЗ §7 (группы событий для перераспределения §30)
    "common", "resource", "loot", "mob", "trap", "rare", "hidden",
    "story", "holiday", "world", "guild", "empty",
)
DEPLETION_TRIGGERS = (  # ТЗ §26.1
    "zero", "below_10pct", "below_count", "manual", "world_event", "zone_state",
)

# Экономические «потолки» награды за одного моба — превышение даёт warning
# (не блок), чтобы конструктор не плодил инфляцию незаметно.
MAX_MOB_EXPERIENCE = 1_000_000
MAX_MOB_COINS = 1_000_000
# Балансные пороги для warning'ов (ТЗ §30/§57): слишком большая группа в бою и
# потенциальная фарм-петля (частый дроп большими пачками).
MAX_MOB_BATTLE_GROUP = 10
FARM_LOOP_DROP_CHANCE = 50.0
FARM_LOOP_DROP_COUNT = 10
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


# Внешние URL картинок блокирует CSP (img-src 'self' data:), поэтому в полях
# изображений разрешены только локальные ассеты (/assets/…) и data:-URI.
_EXTERNAL_URL_RE = re.compile(r"^(?:[a-z][a-z0-9+.-]*:)?//", re.IGNORECASE)


def _is_external_image(value: str) -> bool:
    v = str(value or "").strip()
    return bool(v) and bool(_EXTERNAL_URL_RE.match(v))


def _check_local_image(data: dict[str, Any], key: str, errors: list[str]) -> None:
    value = _str_field(data, key)
    if value and _is_external_image(value):
        errors.append(
            f"Поле «{key}»: внешние URL картинок запрещены (их блокирует CSP). "
            "Загрузите ассет и укажите локальный путь вида /assets/…"
        )


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
    _check_local_image(data, "image", errors)

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


def _warn_farm_loop(rows: Any, warnings: list[str]) -> None:
    """Предупредить о возможной фарм-петле: частый дроп большими пачками (§30)."""
    if not isinstance(rows, list):
        return
    for row in rows:
        if not isinstance(row, dict):
            continue
        chance = _num(row.get("chance"))
        cmax = _num(row.get("max_count"))
        if (chance is not None and chance >= FARM_LOOP_DROP_CHANCE
                and cmax is not None and cmax >= FARM_LOOP_DROP_COUNT):
            warnings.append(
                f"Предмет «{row.get('item_id')}» выпадает часто и большими "
                "пачками — возможна фарм-петля, проверьте лимит/экономику."
            )


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

    # Боевые параметры (ТЗ §8).
    attack_type = _str_field(data, "attack_type")
    if attack_type and attack_type not in MOB_ATTACK_TYPES:
        errors.append(f"Неизвестный тип атаки: {attack_type}.")
    behavior = _str_field(data, "behavior")
    if behavior and behavior not in MOB_BEHAVIOR_TYPES:
        errors.append(f"Неизвестное поведение моба: {behavior}.")
    bmin = _num(data.get("min_in_battle"))
    bmax = _num(data.get("max_in_battle"))
    if bmin is not None and bmin < 1:
        errors.append("Минимум мобов в бою должен быть ≥ 1.")
    if bmin is not None and bmax is not None and bmin > bmax:
        errors.append("Минимум мобов в бою больше максимума.")
    # Балансное предупреждение: слишком большая группа в бою (ТЗ §30/§57).
    if bmax is not None and bmax > MAX_MOB_BATTLE_GROUP:
        warnings.append(
            f"Очень большая группа в бою (до {int(bmax)}) — проверьте баланс."
        )

    for key in ("name", "description"):
        value = _str_field(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")
    _check_local_image(data, "image", errors)

    _validate_drop_rows(data.get("drop"), errors, warnings)
    _warn_farm_loop(data.get("drop"), warnings)

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
    _check_local_image(data, "image", errors)
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


# --- Валидаторы расширенного конструктора локаций --------------------------
def _effect_exists(effect_id: Any) -> bool:
    eid = str(effect_id or "").strip()
    if not eid:
        return False
    try:  # ленивый импорт; реестр недоступен — не валим проверку
        from services.effect_constructor_service import store as effect_store

        return effect_store().get(eid) is not None
    except Exception:
        return True


def _check_chance(data: dict[str, Any], key: str, errors: list[str], label: str) -> float | None:
    """Шанс 0–100 (или None, если поле пустое)."""
    if data.get(key) in (None, ""):
        return None
    value = _num(data.get(key))
    if value is None:
        errors.append(f"{label}: шанс не число.")
    elif value < 0 or value > 100:
        errors.append(f"{label}: шанс должен быть 0–100.")
    return value


def _check_chance_window(data: dict[str, Any], errors: list[str], *, base_key: str = "base_chance", min_key: str = "min_chance") -> None:
    """Минимальный шанс не должен превышать базовый (ТЗ §56)."""
    base = _check_chance(data, base_key, errors, "Базовый шанс")
    minimum = _check_chance(data, min_key, errors, "Минимальный шанс")
    if base is not None and minimum is not None and minimum > base:
        errors.append("Минимальный шанс не может быть выше базового.")


def _check_counts(data: dict[str, Any], errors: list[str], *, min_key: str = "min_count", max_key: str = "max_count") -> None:
    cmin = _num(data.get(min_key)) if data.get(min_key) not in (None, "") else None
    cmax = _num(data.get(max_key)) if data.get(max_key) not in (None, "") else None
    if cmin is not None and cmin < 0:
        errors.append("Минимальное количество не может быть отрицательным.")
    if cmin is not None and cmax is not None and cmin > cmax:
        errors.append("Минимальное количество больше максимального.")


def _check_location_ref(data: dict[str, Any], errors: list[str], *, key: str = "location", required: bool = True) -> None:
    loc = _str_field(data, key)
    if not loc:
        if required:
            errors.append("Не указана локация.")
        return
    if not _location_exists(loc):
        errors.append(f"Локация «{loc}» не существует.")


def _validate_location_zone(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Зона локации и защита от неё (ТЗ §43–44)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not _str_field(data, "name"):
        errors.append("Не заполнено название зоны.")
    ztype = _str_field(data, "type")
    if not ztype:
        errors.append("Не выбран тип зоны.")
    elif ztype not in ZONE_TYPES:
        errors.append(f"Неизвестный тип зоны: {ztype}.")
    _check_location_ref(data, errors)
    _check_chance(data, "trigger_chance", errors, "Срабатывание зоны")

    # Защита от зоны: ссылается на существующие предметы/эффекты (ТЗ §44).
    protections = data.get("protections")
    if protections not in (None, ""):
        if not isinstance(protections, list):
            errors.append("Защита от зоны должна быть списком.")
        else:
            for index, row in enumerate(protections, start=1):
                if not isinstance(row, dict):
                    errors.append(f"Защита {index}: неверный формат.")
                    continue
                item_id = _str_field(row, "item_id")
                effect_id = _str_field(row, "effect_id")
                if not item_id and not effect_id:
                    errors.append(f"Защита {index}: нужен предмет или эффект защиты.")
                if item_id and not _item_exists(item_id):
                    errors.append(f"Защита {index}: предмет «{item_id}» не существует.")
                if effect_id and not _effect_exists(effect_id):
                    errors.append(f"Защита {index}: эффект «{effect_id}» не существует.")
                pct = _num(row.get("percent"))
                if pct is not None and (pct < 0 or pct > 100):
                    errors.append(f"Защита {index}: процент должен быть 0–100.")

    for key in ("name", "player_text", "description"):
        value = _str_field(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")
    return errors, warnings


def _validate_location_resource(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Ресурс локации (ТЗ §13)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    _check_location_ref(data, errors)
    item_id = _str_field(data, "item_id")
    if not item_id:
        errors.append("Не указан предмет-ресурс.")
    elif not _item_exists(item_id):
        errors.append(f"Предмет-ресурс «{item_id}» не существует.")

    category = _str_field(data, "category")
    if category and category not in RESOURCE_CATEGORIES:
        errors.append(f"Неизвестная категория ресурса: {category}.")

    _check_chance_window(data, errors)
    _check_counts(data, errors)

    weekly = data.get("weekly_limit")
    if weekly not in (None, "") and (_num(weekly) is None or _num(weekly) < 0):
        errors.append("Недельный лимит не может быть отрицательным.")
    return errors, warnings


def _validate_location_loot(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Добыча локации (ТЗ §14)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    _check_location_ref(data, errors)
    item_id = _str_field(data, "item_id")
    if not item_id:
        errors.append("Не указан предмет добычи.")
    elif not _item_exists(item_id):
        errors.append(f"Предмет добычи «{item_id}» не существует.")

    source = _str_field(data, "source")
    if not source:
        errors.append("Не указан источник добычи.")
    elif source not in LOOT_SOURCES:
        errors.append(f"Неизвестный источник добычи: {source}.")

    _check_chance_window(data, errors, base_key="chance")
    _check_counts(data, errors)
    weekly = data.get("weekly_limit")
    if weekly not in (None, "") and (_num(weekly) is None or _num(weekly) < 0):
        errors.append("Недельный лимит не может быть отрицательным.")
    return errors, warnings


def _validate_location_mob_spawn(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Появление моба на локации (ТЗ §15)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    _check_location_ref(data, errors)
    mob_id = _str_field(data, "mob_id")
    if not mob_id:
        errors.append("Не указан моб.")
    elif not _mob_exists(mob_id):
        errors.append(f"Моб «{mob_id}» не существует.")

    _check_chance_window(data, errors, base_key="spawn_chance")

    lvl_min = _num(data.get("mob_level_min"))
    lvl_max = _num(data.get("mob_level_max"))
    if lvl_min is not None and lvl_max is not None and lvl_min > lvl_max:
        errors.append("Минимальный уровень моба больше максимального.")

    bmin = _num(data.get("min_in_battle"))
    bmax = _num(data.get("max_in_battle"))
    if bmin is not None and bmin < 1:
        errors.append("Минимум мобов в бою должен быть ≥ 1.")
    if bmin is not None and bmax is not None and bmin > bmax:
        errors.append("Минимум мобов в бою больше максимума.")

    stock = data.get("weekly_stock")
    if stock not in (None, "") and (_num(stock) is None or _num(stock) < 0):
        errors.append("Недельный запас существ не может быть отрицательным.")
    return errors, warnings


def _validate_location_weekly_limit(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Недельный лимит ресурса/моба/дропа/события (ТЗ §16–§26)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    _check_location_ref(data, errors)
    ltype = _str_field(data, "limit_type")
    if not ltype:
        errors.append("Не выбран тип лимита.")
    elif ltype not in WEEKLY_LIMIT_TYPES:
        errors.append(f"Неизвестный тип лимита: {ltype}.")

    # Связанный объект существует — в зависимости от типа лимита.
    linked = _str_field(data, "linked_object")
    if not linked:
        errors.append("Не указан связанный объект лимита.")
    elif ltype in ("resource", "item", "trophy", "mob_drop", "event_item", "guild_resource", "event_currency"):
        if not _item_exists(linked):
            errors.append(f"Связанный предмет «{linked}» не существует.")
    elif ltype in ("mob", "mob_group", "rare_mob", "boss"):
        if not _mob_exists(linked):
            errors.append(f"Связанный моб «{linked}» не существует.")

    source = _str_field(data, "source")
    if source and source not in LOOT_SOURCES:
        errors.append(f"Неизвестный источник получения: {source}.")

    total = data.get("total_stock")
    if total not in (None, "") and (_num(total) is None or _num(total) < 0):
        errors.append("Общий недельный запас не может быть отрицательным.")
    _check_counts(data, errors, min_key="min_per_event", max_key="max_per_event")
    _check_chance_window(data, errors)

    for key in ("depletion_text", "admin_text"):
        value = _str_field(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")
    return errors, warnings


def _validate_location_weekly_rotation(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Недельная ротация ресурсов/мобов/событий (ТЗ §35–§38)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    _check_location_ref(data, errors)
    if not _str_field(data, "name"):
        warnings.append("Не указано название ротации.")

    period = _str_field(data, "periodicity")
    if period and period not in ROTATION_PERIODICITY:
        errors.append(f"Неизвестная периодичность: {period}.")
    mode = _str_field(data, "selection_mode")
    if mode and mode not in ROTATION_SELECTION_MODES:
        errors.append(f"Неизвестный режим выбора: {mode}.")

    for key in ("active_resources", "active_mobs", "active_events"):
        if data.get(key) in (None, ""):
            continue
        value = _num(data.get(key))
        if value is None or value < 0:
            errors.append(f"Поле «{key}» — некорректное число.")
    return errors, warnings


def _validate_location_depletion_rule(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Правило минимального шанса/перераспределения при истощении (ТЗ §26–§30)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    _check_location_ref(data, errors, required=False)
    _check_chance_window(data, errors)

    trigger = _str_field(data, "trigger")
    if trigger and trigger not in DEPLETION_TRIGGERS:
        errors.append(f"Неизвестное условие включения минимального шанса: {trigger}.")
    mode = _str_field(data, "redistribution_mode")
    if mode and mode not in REDISTRIBUTION_MODES:
        errors.append(f"Неизвестный режим перераспределения: {mode}.")
    group = _str_field(data, "event_group")
    if group and group not in EVENT_GROUPS:
        errors.append(f"Неизвестная группа событий: {group}.")
    return errors, warnings


def _validate_location_empty_event(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Особое событие пустой локации (ТЗ §31–§34)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    _check_location_ref(data, errors)
    # Хотя бы один вариант текста для игрока (§33 допускает несколько).
    texts = data.get("texts")
    text = _str_field(data, "player_text")
    if not text and not (isinstance(texts, list) and any(str(t).strip() for t in texts)):
        errors.append("Не заполнен текст события пустой локации.")
    if isinstance(texts, list):
        for t in texts:
            if isinstance(t, str) and t and _has_markup(t):
                errors.append("В тексте пустой локации недопустимая разметка/HTML.")
    if text and _has_markup(text):
        errors.append("В тексте пустой локации недопустимая разметка/HTML.")

    pct = _num(data.get("min_percent_depleted"))
    if pct is not None and (pct < 0 or pct > 100):
        errors.append("Минимальный процент истощённых событий должен быть 0–100.")
    _check_chance(data, "chance", errors, "Событие пустой локации")
    return errors, warnings


def _validate_location_hidden_event(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Скрытое событие локации (ТЗ §10)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not _str_field(data, "admin_name"):
        errors.append("Не заполнено название скрытого события для админки.")
    if not _str_field(data, "player_text"):
        errors.append("Не заполнен текст скрытого события для игрока.")
    _check_location_ref(data, errors)
    # Скрытое событие обязано иметь условия открытия (§10).
    conditions = data.get("conditions")
    if not conditions:
        errors.append("У скрытого события должны быть условия открытия.")
    _check_chance(data, "open_chance", errors, "Открытие скрытого события")

    _check_item_ref(data, "given_item", "Выдаваемый предмет", errors)
    battle_mob = _str_field(data, "battle_mob")
    if battle_mob and not _mob_exists(battle_mob):
        errors.append(f"Запускаемый моб «{battle_mob}» не существует.")

    for key in ("admin_name", "player_text", "player_name"):
        value = _str_field(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")
    return errors, warnings


def _validate_location_event_answer(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Вариант ответа в событии, в т.ч. скрытый (ТЗ §11)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not _str_field(data, "button_text"):
        errors.append("Не заполнен текст кнопки варианта ответа.")
    if not _str_field(data, "result_text") and not _str_field(data, "result"):
        errors.append("У варианта ответа должен быть результат.")

    result = _str_field(data, "result")
    if result and result not in EVENT_RESULT_TYPES:
        errors.append(f"Неизвестный результат варианта: {result}.")

    # Скрытый вариант обязан иметь условия показа (§11.3).
    if data.get("hidden") and not data.get("conditions"):
        errors.append("У скрытого варианта ответа должны быть условия показа.")

    _check_item_ref(data, "required_item", "Требуемый предмет", errors)
    _check_item_ref(data, "reward_item", "Награда-предмет", errors)
    _check_chance(data, "success_chance", errors, "Шанс успеха")
    _check_chance(data, "fail_chance", errors, "Шанс провала")

    for key in ("button_text", "result_text"):
        value = _str_field(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")
    return errors, warnings


# --- Валидаторы расширенного конструктора мобов ----------------------------
def _zone_exists(zone_id: Any) -> bool:
    zid = str(zone_id or "").strip()
    return bool(zid) and get_content(KIND_LOCATION_ZONE, zid) is not None


def _event_exists(event_id: Any) -> bool:
    eid = str(event_id or "").strip()
    if not eid:
        return False
    return (get_content(KIND_EVENT, eid) is not None
            or get_content(KIND_LOCATION_HIDDEN_EVENT, eid) is not None)


def _check_mob_ref(data: dict[str, Any], errors: list[str]) -> None:
    mob_id = _str_field(data, "mob_id")
    if not mob_id:
        errors.append("Не указан моб.")
    elif not _mob_exists(mob_id):
        errors.append(f"Моб «{mob_id}» не существует.")


def _validate_mob_variant(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Вариант моба (обычный/усиленный/элитный/босс… ТЗ §6)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not _str_field(data, "name"):
        errors.append("Не заполнено название варианта.")
    _check_mob_ref(data, errors)
    vtype = _str_field(data, "variant_type")
    if vtype and vtype not in MOB_VARIANT_TYPES:
        errors.append(f"Неизвестный тип варианта: {vtype}.")

    # Множители не отрицательные.
    for key in ("hp_mult", "damage_mult", "defense_mult", "accuracy_mult",
                "evasion_mult", "exp_mult", "coins_mult", "drop_mult"):
        if data.get(key) in (None, ""):
            continue
        value = _num(data.get(key))
        if value is None:
            errors.append(f"Множитель «{key}» — не число.")
        elif value < 0:
            errors.append(f"Множитель «{key}» не может быть отрицательным.")

    _check_chance(data, "spawn_chance", errors, "Появление варианта")
    for key in ("name", "description"):
        value = _str_field(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")
    return errors, warnings


def _validate_mob_skill(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Навык моба (ТЗ §9)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not _str_field(data, "name"):
        errors.append("Не заполнено название навыка.")
    _check_mob_ref(data, errors)
    stype = _str_field(data, "skill_type")
    if stype and stype not in MOB_SKILL_TYPES:
        errors.append(f"Неизвестный тип навыка: {stype}.")
    cond = _str_field(data, "use_condition")
    if cond and cond not in MOB_SKILL_CONDITIONS:
        errors.append(f"Неизвестное условие использования: {cond}.")

    _check_chance(data, "use_chance", errors, "Использование навыка")
    cooldown = _num(data.get("cooldown"))
    if cooldown is not None and cooldown < 0:
        errors.append("Кулдаун не может быть отрицательным.")

    for key in ("name", "player_text", "player_description"):
        value = _str_field(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")
    return errors, warnings


def _validate_mob_passive(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Пассивная особенность моба (ТЗ §10)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not _str_field(data, "name"):
        errors.append("Не заполнено название особенности.")
    _check_mob_ref(data, errors)
    for key in ("name", "player_description", "description"):
        value = _str_field(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")
    return errors, warnings


def _validate_mob_resistance(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Сопротивление или слабость моба (ТЗ §11)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    _check_mob_ref(data, errors)
    rtype = _str_field(data, "resist_type")
    if not rtype:
        errors.append("Не выбран тип сопротивления/слабости.")
    elif rtype not in MOB_RESIST_TYPES:
        errors.append(f"Неизвестный тип сопротивления/слабости: {rtype}.")
    if data.get("value") not in (None, "") and _num(data.get("value")) is None:
        errors.append("Значение сопротивления — не число.")
    return errors, warnings


def _validate_mob_effect(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Эффект, который моб накладывает/получает (ТЗ §12)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not _str_field(data, "name"):
        errors.append("Не заполнено название эффекта.")
    _check_mob_ref(data, errors)
    effect_id = _str_field(data, "effect_id")
    if effect_id and not _effect_exists(effect_id):
        errors.append(f"Эффект «{effect_id}» не существует.")
    _check_chance(data, "chance", errors, "Наложение эффекта")
    duration = _num(data.get("duration"))
    if duration is not None and duration < 0:
        errors.append("Длительность не может быть отрицательной.")
    for key in ("name", "player_text"):
        value = _str_field(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")
    return errors, warnings


def _validate_mob_event_link(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Привязка моба к (скрытому) событию (ТЗ §16)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    _check_mob_ref(data, errors)
    event_id = _str_field(data, "event_id")
    if not event_id:
        errors.append("Не указано событие.")
    elif not _event_exists(event_id):
        errors.append(f"Событие «{event_id}» не существует.")
    _check_chance(data, "spawn_chance", errors, "Появление в событии")
    count = _num(data.get("count"))
    if count is not None and count < 1:
        errors.append("Количество мобов в событии должно быть ≥ 1.")
    variant = _str_field(data, "variant_type")
    if variant and variant not in MOB_VARIANT_TYPES:
        errors.append(f"Неизвестный вариант моба: {variant}.")
    return errors, warnings


def _validate_mob_zone_link(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Связь моба с зоной локации (ТЗ §21)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    _check_mob_ref(data, errors)
    zone_id = _str_field(data, "zone_id")
    if not zone_id:
        errors.append("Не указана зона.")
    elif not _zone_exists(zone_id):
        errors.append(f"Зона «{zone_id}» не существует.")
    if data.get("spawn_chance_delta") not in (None, "") and _num(data.get("spawn_chance_delta")) is None:
        errors.append("Изменение шанса встречи — не число.")
    variant = _str_field(data, "variant_type")
    if variant and variant not in MOB_VARIANT_TYPES:
        errors.append(f"Неизвестный вариант моба: {variant}.")
    return errors, warnings


def _validate_mob_phase(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Фаза боя босса (ТЗ §26)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not _str_field(data, "name"):
        errors.append("Не заполнено название фазы.")
    _check_mob_ref(data, errors)
    if not _str_field(data, "start_condition"):
        warnings.append("Не указано условие начала фазы.")
    for key in ("name", "player_text", "transition_message"):
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
    KIND_LOCATION_ZONE: _validate_location_zone,
    KIND_LOCATION_RESOURCE: _validate_location_resource,
    KIND_LOCATION_LOOT: _validate_location_loot,
    KIND_LOCATION_MOB_SPAWN: _validate_location_mob_spawn,
    KIND_LOCATION_WEEKLY_LIMIT: _validate_location_weekly_limit,
    KIND_LOCATION_WEEKLY_ROTATION: _validate_location_weekly_rotation,
    KIND_LOCATION_DEPLETION_RULE: _validate_location_depletion_rule,
    KIND_LOCATION_EMPTY_EVENT: _validate_location_empty_event,
    KIND_LOCATION_HIDDEN_EVENT: _validate_location_hidden_event,
    KIND_LOCATION_EVENT_ANSWER: _validate_location_event_answer,
    KIND_MOB_VARIANT: _validate_mob_variant,
    KIND_MOB_SKILL: _validate_mob_skill,
    KIND_MOB_PASSIVE: _validate_mob_passive,
    KIND_MOB_RESISTANCE: _validate_mob_resistance,
    KIND_MOB_EFFECT: _validate_mob_effect,
    KIND_MOB_EVENT_LINK: _validate_mob_event_link,
    KIND_MOB_ZONE_LINK: _validate_mob_zone_link,
    KIND_MOB_PHASE: _validate_mob_phase,
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
