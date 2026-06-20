"""Достижения V2 (ТЗ «Система достижений») — авторская часть.

Слой данных + валидация определений достижений и их категорий. Хранение через
генерик EntityStore (data/achievements.json, data/achievement_categories.json).
Аудит и права — в роутере (admin_achievement_api) через admin_operation.

Здесь — КОНСТРУКТОР достижений (создать/проверить/опубликовать без кода).
Achievement engine (авто-выдача по действиям игрока, прогресс, история, ручная
выдача/откат живым игрокам) — отдельный runtime-слой, добавится позже.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from services.admin_entity_store import EntityStore

# --- Статусы (как у конструктора мира) --------------------------------------
STATUS_DRAFT = "draft"
STATUS_REVIEW = "review"
STATUS_READY = "ready"
STATUS_PUBLISHED = "published"
STATUS_DISABLED = "disabled"
STATUS_ERROR = "error"
STATUS_ARCHIVE = "archive"

STATUSES = (
    STATUS_DRAFT, STATUS_REVIEW, STATUS_READY,
    STATUS_PUBLISHED, STATUS_DISABLED, STATUS_ERROR, STATUS_ARCHIVE,
)
STATUS_LABELS = {
    STATUS_DRAFT: "Черновик",
    STATUS_REVIEW: "На проверке",
    STATUS_READY: "Готово к публикации",
    STATUS_PUBLISHED: "Опубликовано",
    STATUS_DISABLED: "Отключено",
    STATUS_ERROR: "Ошибка проверки",
    STATUS_ARCHIVE: "Архив",
}
TRANSITIONS: dict[str, set[str]] = {
    STATUS_DRAFT: {STATUS_REVIEW, STATUS_READY, STATUS_ARCHIVE, STATUS_ERROR},
    STATUS_REVIEW: {STATUS_DRAFT, STATUS_READY, STATUS_ARCHIVE, STATUS_ERROR},
    STATUS_READY: {STATUS_DRAFT, STATUS_PUBLISHED, STATUS_ARCHIVE, STATUS_ERROR},
    STATUS_PUBLISHED: {STATUS_DISABLED, STATUS_ARCHIVE},
    STATUS_DISABLED: {STATUS_PUBLISHED, STATUS_DRAFT, STATUS_ARCHIVE},
    STATUS_ERROR: {STATUS_DRAFT, STATUS_REVIEW, STATUS_ARCHIVE},
    STATUS_ARCHIVE: set(),
}

# --- Справочники (ТЗ §3,6,7,9,10,11,14) -------------------------------------
ACHIEVEMENT_TYPES = (
    "normal", "hidden", "story", "combat", "craft", "exploration", "economy",
    "fishing", "alchemy", "forge", "social", "guild", "raid", "world",
    "festive", "seasonal", "unique", "one_time", "repeatable", "multi_stage",
)
RARITIES = (
    "common", "uncommon", "rare", "epic", "legendary",
    "mythic", "divine", "unique",
)
VISIBILITIES = (
    "open", "hidden_until_earned", "fully_hidden", "story",
    "seasonal", "guild", "admin",
)
CONDITION_LOGIC = ("any", "all", "ordered", "n_of")
CONDITION_TYPES = (
    "reach_level", "kill_mob", "kill_boss", "kill_world_boss",
    "damage_world_boss", "join_raid", "finish_raid", "find_item", "craft_item",
    "sell_item", "buy_item", "catch_fish", "open_clam", "find_pearl",
    "visit_location", "discover_location", "finish_event", "use_promo",
    "get_fine", "pay_fine", "survive_raid_event", "get_warning",
    "no_warnings_days", "join_guild", "create_guild", "contribute_guild",
    "finish_guild_quest", "join_world_event", "contribute_global_progress",
    "get_unique_item", "use_artifact", "revive_by_artifact",
)
PROGRESS_TYPES = (
    "numeric", "percent", "list", "stages", "contribution", "guild", "world",
)
REWARD_TYPES = (
    "experience", "coins", "item", "unique_item", "exp_grains", "stat_points",
    "skill_points", "temp_buff", "passive_bonus", "title", "emblem",
    "profile_icon", "unlock_location", "unlock_npc", "unlock_recipe",
    "unlock_event", "guild_points", "event_currency",
)
REPEAT_PERIODS = ("day", "week", "month", "season", "festive")

# Лимит «слишком большой награды» (ТЗ §23) — мягкое предупреждение.
MAX_REWARD_EXP = 10_000_000
MAX_REWARD_COINS = 100_000_000_000
_CURRENCY_ITEM_IDS = {"money_copper", "money_silver", "money_gold"}

_store = EntityStore(
    env_var="ACHIEVEMENTS_PATH",
    default_rel="data/achievements.json",
    statuses=STATUSES,
    transitions=TRANSITIONS,
    initial_status=STATUS_DRAFT,
)
# Категории — лёгкие сущности (active/archive), отдельный файл.
_categories = EntityStore(
    env_var="ACHIEVEMENT_CATEGORIES_PATH",
    default_rel="data/achievement_categories.json",
    statuses=("active", "archive"),
    transitions={"active": {"archive"}, "archive": {"active"}},
    initial_status="active",
)


def store() -> EntityStore:
    return _store


def categories() -> EntityStore:
    return _categories


def _has_markup(value: str) -> bool:
    low = value.lower()
    return "<script" in low or ("<" in value and ">" in value)


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _item_exists(item_id: str) -> bool:
    iid = str(item_id or "").strip()
    if not iid:
        return False
    if iid in _CURRENCY_ITEM_IDS:
        return True
    try:
        from services.item_registry import get_item_definition_by_id
        return get_item_definition_by_id(iid) is not None
    except Exception:
        return True


def _category_exists(cat_id: str) -> bool:
    return bool(str(cat_id or "").strip()) and _categories.get(str(cat_id)) is not None


def _validate_conditions(data: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    logic = str(data.get("condition_logic") or "").strip()
    if logic and logic not in CONDITION_LOGIC:
        errors.append(f"Неизвестный режим условий: {logic}.")
    conditions = data.get("conditions")
    if conditions in (None, ""):
        errors.append("Не указаны условия получения.")
        return
    if not isinstance(conditions, list) or not conditions:
        errors.append("Условия должны быть непустым списком.")
        return
    for i, cond in enumerate(conditions, start=1):
        if not isinstance(cond, dict):
            errors.append(f"Условие {i}: неверный формат.")
            continue
        ctype = str(cond.get("type") or "").strip()
        if not ctype:
            errors.append(f"Условие {i}: не выбран тип.")
        elif ctype not in CONDITION_TYPES:
            errors.append(f"Условие {i}: неизвестный тип «{ctype}».")
        amount = cond.get("amount")
        if amount not in (None, "") and (_num(amount) is None or _num(amount) < 0):
            errors.append(f"Условие {i}: некорректное количество.")
    if logic == "n_of":
        n = _num(data.get("condition_n"))
        if n is None or n < 1:
            errors.append("Для режима «N из списка» укажите N ≥ 1.")


def _validate_rewards(data: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    rewards = data.get("rewards")
    if rewards in (None, ""):
        return
    if not isinstance(rewards, list):
        errors.append("Награды должны быть списком.")
        return
    for i, rw in enumerate(rewards, start=1):
        if not isinstance(rw, dict):
            errors.append(f"Награда {i}: неверный формат.")
            continue
        rtype = str(rw.get("type") or "").strip()
        if rtype and rtype not in REWARD_TYPES:
            errors.append(f"Награда {i}: неизвестный тип «{rtype}».")
        if rtype in ("item", "unique_item"):
            item_id = str(rw.get("item_id") or "").strip()
            if not item_id:
                errors.append(f"Награда {i}: не указан предмет.")
            elif not _item_exists(item_id):
                errors.append(f"Награда {i}: предмет «{item_id}» не существует.")
        if rtype == "experience":
            value = _num(rw.get("amount"))
            if value is not None and value > MAX_REWARD_EXP:
                warnings.append(f"Награда {i}: очень большой опыт.")
        if rtype == "coins":
            value = _num(rw.get("amount"))
            if value is not None and value > MAX_REWARD_COINS:
                warnings.append(f"Награда {i}: очень много валюты.")


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    """Проверка достижения перед публикацией (ТЗ §23)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not str(data.get("name") or "").strip():
        errors.append("Не заполнено название достижения.")
    if not str(data.get("description") or "").strip() and not str(data.get("short_description") or "").strip():
        errors.append("Нужно хотя бы краткое описание.")

    a_type = str(data.get("type") or "").strip()
    if a_type and a_type not in ACHIEVEMENT_TYPES:
        errors.append(f"Неизвестный тип достижения: {a_type}.")
    rarity = str(data.get("rarity") or "").strip()
    if rarity and rarity not in RARITIES:
        errors.append(f"Неизвестная редкость: {rarity}.")
    visibility = str(data.get("visibility") or "").strip()
    if visibility and visibility not in VISIBILITIES:
        errors.append(f"Неизвестная видимость: {visibility}.")
    progress_type = str(data.get("progress_type") or "").strip()
    if progress_type and progress_type not in PROGRESS_TYPES:
        errors.append(f"Неизвестный тип прогресса: {progress_type}.")

    category = str(data.get("category") or "").strip()
    if not category:
        errors.append("Не выбрана категория.")
    elif not _category_exists(category):
        errors.append(f"Категория «{category}» не существует.")

    _validate_conditions(data, errors, warnings)
    _validate_rewards(data, errors, warnings)

    # Скрытое достижение не должно раскрывать условия в видимом описании.
    if visibility in ("hidden_until_earned", "fully_hidden"):
        desc = str(data.get("description") or "")
        if any(marker in desc.lower() for marker in ("услови", "нужно ", "требуется")):
            warnings.append("Скрытое достижение, похоже, раскрывает условия в описании.")

    # Повторяемость.
    if data.get("repeatable"):
        period = str(data.get("repeat_period") or "").strip()
        if period and period not in REPEAT_PERIODS:
            errors.append(f"Неизвестный период повтора: {period}.")

    # Сезонные даты.
    start = _parse_date(data.get("start_date"))
    end = _parse_date(data.get("end_date"))
    if start and end and end <= start:
        errors.append("Дата окончания должна быть позже даты начала.")

    # Многоступенчатость.
    stages = data.get("stages")
    if isinstance(stages, list):
        for i, st in enumerate(stages, start=1):
            if isinstance(st, dict):
                req = _num(st.get("required_progress"))
                if req is not None and req < 0:
                    errors.append(f"Ступень {i}: прогресс не может быть отрицательным.")

    for key in ("name", "short_description", "description"):
        value = str(data.get(key) or "").strip()
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def validate_category(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    if not str(data.get("name") or "").strip():
        errors.append("Не заполнено название категории.")
    return {"ok": not errors, "errors": errors, "warnings": []}
