"""Конструктор предметов V2 (ТЗ «Конструктор предметов») — авторская часть.

Слой данных + валидация определений предметов, история версий и индекс
«где используется». Хранение — генерик EntityStore (data/item_constructor.json).
Аудит и права — в роутере (admin_item_api) через admin_operation.

Это КОНСТРУКТОР (создать/проверить/опубликовать/версии без кода). Реальное
чтение опубликованных предметов игрой (рядом со статичным item_registry) —
отдельный runtime-слой на вырост.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from services.admin_entity_store import EntityStore

# --- Статусы (ТЗ §28) -------------------------------------------------------
STATUS_DRAFT = "draft"
STATUS_REVIEW = "review"
STATUS_READY = "ready"
STATUS_PUBLISHED = "published"
STATUS_DISABLED = "disabled"
STATUS_ARCHIVE = "archive"
STATUS_DELETED_SOFT = "deleted_soft"
STATUS_ERROR = "error"

STATUSES = (
    STATUS_DRAFT, STATUS_REVIEW, STATUS_READY, STATUS_PUBLISHED,
    STATUS_DISABLED, STATUS_ARCHIVE, STATUS_DELETED_SOFT, STATUS_ERROR,
)
STATUS_LABELS = {
    STATUS_DRAFT: "Черновик",
    STATUS_REVIEW: "На проверке",
    STATUS_READY: "Готов к публикации",
    STATUS_PUBLISHED: "Опубликован",
    STATUS_DISABLED: "Отключён",
    STATUS_ARCHIVE: "Архив",
    STATUS_DELETED_SOFT: "Удалён мягко",
    STATUS_ERROR: "Ошибка проверки",
}
TRANSITIONS: dict[str, set[str]] = {
    STATUS_DRAFT: {STATUS_REVIEW, STATUS_READY, STATUS_ARCHIVE, STATUS_ERROR, STATUS_DELETED_SOFT},
    STATUS_REVIEW: {STATUS_DRAFT, STATUS_READY, STATUS_ARCHIVE, STATUS_ERROR},
    STATUS_READY: {STATUS_DRAFT, STATUS_PUBLISHED, STATUS_ARCHIVE, STATUS_ERROR},
    STATUS_PUBLISHED: {STATUS_DISABLED, STATUS_ARCHIVE, STATUS_DELETED_SOFT},
    STATUS_DISABLED: {STATUS_PUBLISHED, STATUS_DRAFT, STATUS_ARCHIVE, STATUS_DELETED_SOFT},
    STATUS_ARCHIVE: {STATUS_DELETED_SOFT, STATUS_DRAFT},
    STATUS_DELETED_SOFT: {STATUS_ARCHIVE, STATUS_DRAFT},
    STATUS_ERROR: {STATUS_DRAFT, STATUS_REVIEW, STATUS_ARCHIVE},
}

# --- Справочники (ТЗ §6–8,12,13,14,27) --------------------------------------
ITEM_CATEGORIES = (
    "Оружие", "Броня", "Щит", "Посох", "Магическая книга", "Боеприпасы",
    "Метательное", "Зелье", "Боевой расходник", "Ресурс", "Руда", "Слиток",
    "Пластина", "Кожа", "Ткань", "Алхимический ингредиент", "Рыба", "Улов",
    "Драгоценный камень", "Артефакт", "Особый предмет", "Квестовый предмет",
    "Трофей", "Рецепт", "Еда", "Напиток", "Инструмент", "Сумка / карман",
    "Событийный предмет", "Гильдейский предмет", "Системная награда",
)
ITEM_TYPES = (
    "normal", "equippable", "consumable", "resource", "ingredient", "recipe",
    "quest", "unique", "artifact", "one_time_artifact", "special_slot",
    "craft", "sale", "event", "guild", "raid", "achievement",
)
QUALITIES = ("common", "uncommon", "rare", "epic", "legendary", "mythic", "divine")
EQUIP_SLOTS = (
    "head", "chest", "legs", "gloves", "boots", "belt", "main_hand",
    "off_hand", "two_hands", "staff", "spellbook", "shield", "ring",
    "necklace", "special", "bag",
)
TAGS = (
    "starter", "market", "port_market", "black_market", "event", "festive",
    "guild", "raid", "unique", "test", "hidden", "deprecated", "no_grant",
    "admin_only",
)
# Подмножества для подсказок/мягкой проверки (движок поддерживает не всё — §34).
PROPERTY_TYPES = (
    "strength", "stamina", "agility", "perception", "intelligence", "wisdom",
    "hp", "mana", "spirit", "energy", "phys_defense", "mag_defense", "accuracy",
    "evasion", "crit_chance", "crit_damage", "armor", "hp_regen", "mana_regen",
    "exp_bonus", "coin_bonus", "loot_bonus", "fishing_bonus", "alchemy_bonus",
)
EFFECT_TYPES = (
    "one_time", "passive_on_equip", "temp_on_use", "stacking", "combat",
    "loot", "fishing", "alchemy", "craft", "zone_protection", "revive",
    "reflect", "thorns", "vampirism", "burn", "poison", "stun", "bleed",
    "cleanse", "regen",
)
PRICE_SELL_CAP = 1_000_000_000_000  # 1e12 меди — мягкий предупредительный лимит

_store = EntityStore(
    env_var="ITEM_CONSTRUCTOR_PATH",
    default_rel="data/item_constructor.json",
    statuses=STATUSES,
    transitions=TRANSITIONS,
    initial_status=STATUS_DRAFT,
)


def store() -> EntityStore:
    return _store


def _has_markup(value: str) -> bool:
    low = value.lower()
    return "<script" in low or ("<" in value and ">" in value)


# Внешние URL картинок блокирует CSP (img-src 'self' data:) — в полях картинок
# допустимы только локальные ассеты (/assets/…) и data:-URI.
_EXTERNAL_IMG_RE = re.compile(r"^(?:[a-z][a-z0-9+.-]*:)?//", re.IGNORECASE)


def _is_external_image(value: str) -> bool:
    v = str(value or "").strip()
    return bool(v) and bool(_EXTERNAL_IMG_RE.match(v))


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    """Проверка предмета перед публикацией (ТЗ §25)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not str(data.get("name") or "").strip():
        errors.append("Не заполнено название.")
    if not str(data.get("description") or "").strip() and not str(data.get("short_description") or "").strip():
        errors.append("Нужно хотя бы краткое описание для игрока.")
    if not str(data.get("category") or "").strip():
        errors.append("Не указана категория.")

    item_type = str(data.get("item_type") or "").strip()
    if item_type and item_type not in ITEM_TYPES:
        errors.append(f"Неизвестный тип предмета: {item_type}.")
    quality = str(data.get("quality") or "").strip()
    if quality and quality not in QUALITIES:
        errors.append(f"Неизвестное качество: {quality}.")

    for key in ("price_buy", "price_sell"):
        value = _num(data.get(key))
        if value is None:
            continue
        if value < 0:
            errors.append(f"Цена «{key}» не может быть отрицательной.")
    sell = _num(data.get("price_sell"))
    if sell is not None and sell > PRICE_SELL_CAP:
        warnings.append("Очень высокая цена продажи — проверьте экономику.")

    stackable = bool(data.get("stackable"))
    max_stack = _num(data.get("max_stack"))
    if stackable:
        if max_stack is None or max_stack < 1:
            errors.append("Стакающийся предмет должен иметь максимальный стак ≥ 1.")
    else:
        if max_stack is not None and max_stack > 1:
            errors.append("Нестакаемый предмет не может иметь стак больше 1.")

    if data.get("equippable"):
        slot = str(data.get("equip_slot") or "").strip()
        if not slot:
            errors.append("Экипируемый предмет должен иметь слот экипировки.")
        elif slot not in EQUIP_SLOTS:
            errors.append(f"Неизвестный слот экипировки: {slot}.")
        if data.get("two_handed") and slot not in ("two_hands", "staff", "main_hand"):
            warnings.append("Двуручный предмет обычно занимает слот двух рук.")

    properties = data.get("properties")
    if isinstance(properties, list):
        for i, prop in enumerate(properties, start=1):
            if not isinstance(prop, dict):
                errors.append(f"Свойство {i}: неверный формат.")
                continue
            ptype = str(prop.get("type") or "").strip()
            if ptype and ptype not in PROPERTY_TYPES:
                warnings.append(f"Свойство {i}: тип «{ptype}» не из стандартного набора движка.")
            if prop.get("value") not in (None, "") and _num(prop.get("value")) is None:
                errors.append(f"Свойство {i}: значение не число.")

    effects = data.get("effects")
    if isinstance(effects, list):
        for i, eff in enumerate(effects, start=1):
            etype = str((eff or {}).get("type") or "").strip() if isinstance(eff, dict) else ""
            if etype and etype not in EFFECT_TYPES:
                warnings.append(f"Эффект {i}: тип «{etype}» не из стандартного набора движка.")

    for key in ("name", "short_description", "description"):
        value = str(data.get(key) or "").strip()
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")

    for key in ("image", "icon", "image_url"):
        value = str(data.get(key) or "").strip()
        if value and _is_external_image(value):
            errors.append(
                f"Поле «{key}»: внешние URL картинок запрещены (их блокирует CSP). "
                "Загрузите ассет и укажите локальный путь вида /assets/…"
            )

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def record_version(item_id: str, *, by: str = "", reason: str = "") -> dict[str, Any] | None:
    """Снять снапшот текущих данных предмета в историю версий (ТЗ §21)."""
    envelope = _store.get(item_id)
    if envelope is None:
        return None
    data = dict(envelope.get("data") or {})
    history = [h for h in data.get("version_history", []) if isinstance(h, dict)]
    snapshot = {k: v for k, v in data.items() if k != "version_history"}
    history.append({
        "version": int(envelope.get("version") or 1),
        "at": _now_iso(),
        "by": str(by or ""),
        "reason": str(reason or ""),
        "snapshot": snapshot,
    })
    # Ограничим историю, чтобы файл не разрастался.
    if len(history) > 50:
        history = history[-50:]
    return _store.update(item_id, {"version_history": history}, actor=by)


# --- Индекс «где используется» (ТЗ §20) -------------------------------------
def where_used(item_id: str) -> dict[str, Any]:
    """Найти ссылки на предмет в реестрах мира/достижений/крафте."""
    item_id = str(item_id or "").strip()
    used: dict[str, list[dict[str, Any]]] = {
        "mob_drops": [], "events": [], "quests": [], "achievements": [], "recipes": [],
    }
    if not item_id:
        return used

    try:
        from services import world_content_registry as world

        for mob in world.list_content(world.KIND_MOB):
            drop = (mob.get("data") or {}).get("drop")
            if isinstance(drop, list) and any(str((r or {}).get("item_id")) == item_id for r in drop if isinstance(r, dict)):
                used["mob_drops"].append({"id": mob.get("id"), "name": (mob.get("data") or {}).get("name")})
        for ev in world.list_content(world.KIND_EVENT):
            d = ev.get("data") or {}
            if item_id in (str(d.get("given_item") or ""), str(d.get("required_item") or ""), str(d.get("consumed_item") or "")):
                used["events"].append({"id": ev.get("id"), "name": d.get("name")})
        for quest in world.list_content(world.KIND_QUEST):
            d = quest.get("data") or {}
            if d.get("goal_type") in ("bring_item", "deliver_item") and str(d.get("goal_target") or "") == item_id:
                used["quests"].append({"id": quest.get("id"), "name": d.get("name")})
    except Exception:
        pass

    try:
        from services import achievement_service as ach

        for env in ach.store().list():
            for rw in (env.get("data") or {}).get("rewards", []) or []:
                if isinstance(rw, dict) and str(rw.get("item_id") or "") == item_id:
                    used["achievements"].append({"id": env.get("id"), "name": (env.get("data") or {}).get("name")})
                    break
    except Exception:
        pass

    try:
        from services.item_registry import load_all_item_definitions  # ensure module importable

        from project_paths import resolve_project_path
        import json as _json

        recipes_path = resolve_project_path("data/crafting_recipes.json")
        if recipes_path.exists():
            recipes = _json.loads(recipes_path.read_text(encoding="utf-8"))
            entries = recipes.values() if isinstance(recipes, dict) else recipes
            for recipe in entries or []:
                if not isinstance(recipe, dict):
                    continue
                blob = _json.dumps(recipe, ensure_ascii=False)
                if f'"{item_id}"' in blob:
                    used["recipes"].append({"id": recipe.get("id") or recipe.get("recipe_id"), "name": recipe.get("name")})
    except Exception:
        pass

    used["total"] = sum(len(v) for v in used.values() if isinstance(v, list))
    return used
