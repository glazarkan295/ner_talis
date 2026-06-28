"""Конструктор жилого района / дома игрока (ТЗ 21 §6).

Запись = план жилья (тип участка + дом) с вложенными коллекциями: специальные
комнаты (§6.3), неулучшаемые постройки (§6.2), улучшаемые постройки (§6.4),
блюда домашней готовки (§6.5) и настройки отдыха (§6.6).

Все значения таблиц §6.1–§6.3 — это значения по умолчанию (PLOT_PRESETS/
ROOM_PRESETS) для подсказок UI; админ редактирует их в записи.

Хранение — EntityStore (data/housing_constructor.json). Слой данных + валидация
+ предпросмотр.
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")

# Типы участков и домов (§6.1).
PLOT_TYPES = ("small", "medium", "large")
PLOT_TYPE_LABELS = {"small": "Малый участок", "medium": "Средний участок", "large": "Большой участок"}
HOUSE_TYPES = ("small", "normal", "large")
HOUSE_TYPE_LABELS = {"small": "Малый дом", "normal": "Обычный дом", "large": "Большой дом"}
# Уровень готовки/блюд (§6.1/§6.5).
COOKING_TIERS = ("common", "unusual", "special")
COOKING_TIER_LABELS = {
    "common": "Обычные блюда", "unusual": "Блюда с необычными эффектами",
    "special": "Блюда с особыми эффектами",
}
DISH_TYPES = COOKING_TIERS
DISH_TYPE_LABELS = COOKING_TIER_LABELS
# Характеристики (для комнат §6.3) — совпадают с таверной.
STAT_KEYS = ("strength", "endurance", "agility", "perception", "intelligence", "wisdom")
STAT_LABELS = {
    "strength": "Сила", "endurance": "Выносливость", "agility": "Ловкость",
    "perception": "Восприятие", "intelligence": "Интеллект", "wisdom": "Мудрость",
}
# Специальные комнаты (§6.3).
SPECIAL_ROOM_TYPES = ("gym", "reaction_hall", "meditation_room")
SPECIAL_ROOM_LABELS = {
    "gym": "Тренажёрный зал", "reaction_hall": "Зал реакции",
    "meditation_room": "Комната медитации и знаний",
}
# Неулучшаемые постройки (§6.2).
FIXED_BUILDINGS = (
    "jewelry_station", "leather_station", "blacksmith_station", "smelter",
    "mailbox", "trophy_room",
)
FIXED_BUILDING_LABELS = {
    "jewelry_station": "Домашний ювелирный станок", "leather_station": "Домашний кожевенный станок",
    "blacksmith_station": "Домашний кузнечный станок", "smelter": "Домашняя плавильня",
    "mailbox": "Почтовый ящик", "trophy_room": "Комната трофеев",
}
# Улучшаемые постройки (§6.4).
UPGRADABLE_BUILDINGS = ("warehouse", "greenhouse", "altar", "pond")
UPGRADABLE_BUILDING_LABELS = {
    "warehouse": "Склад", "greenhouse": "Оранжерея", "altar": "Алтарь", "pond": "Пруд",
}
CURRENCIES = ("copper", "silver", "gold", "magic_gold", "ancient_coin")

# Значения по умолчанию таблицы §6.1 (минуты отдыха, готовка, доп. постройки).
PLOT_PRESETS = {
    "small": {"house_type": "small", "cooking_tier": "common", "full_rest_minutes": 90,
              "base_features": ["mailbox"], "extra_building_slots": 1},
    "medium": {"house_type": "normal", "cooking_tier": "unusual", "full_rest_minutes": 60,
               "base_features": ["special_room", "mailbox"], "extra_building_slots": 3},
    "large": {"house_type": "large", "cooking_tier": "special", "full_rest_minutes": 40,
              "base_features": ["special_room", "trophy_room", "mailbox"], "extra_building_slots": 5},
}
# Значения по умолчанию комнат §6.3 (30 минут, 40%, 1 раз в день).
ROOM_PRESETS = {
    "gym": {"stats": ["strength", "endurance"], "time_minutes": 30, "chance_percent": 40, "daily_limit": 1},
    "reaction_hall": {"stats": ["agility", "perception"], "time_minutes": 30, "chance_percent": 40, "daily_limit": 1},
    "meditation_room": {"stats": ["intelligence", "wisdom"], "time_minutes": 30, "chance_percent": 40, "daily_limit": 1},
}

_store = EntityStore(
    env_var="HOUSING_CONSTRUCTOR_PATH",
    default_rel="data/housing_constructor.json",
    statuses=STATUSES,  # noqa: F405
    transitions=TRANSITIONS,  # noqa: F405
    initial_status=STATUS_DRAFT,  # noqa: F405
)


def store() -> EntityStore:
    return _store


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_html(value: Any) -> bool:
    s = str(value or "")
    return bool(_HTML_RE.search(s)) or "<script" in s.lower()


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not str(data.get("name") or "").strip():
        errors.append("Не заполнено название плана жилья.")

    plot = str(data.get("plot_type") or "").strip()
    if plot and plot not in PLOT_TYPES:
        warnings.append(f"Тип участка «{plot}» не из списка.")
    house = str(data.get("house_type") or "").strip()
    if house and house not in HOUSE_TYPES:
        warnings.append(f"Тип дома «{house}» не из списка.")
    tier = str(data.get("cooking_tier") or "").strip()
    if tier and tier not in COOKING_TIERS:
        warnings.append(f"Уровень готовки «{tier}» не из списка.")

    for key, label in (("full_rest_minutes", "Время отдыха до полного восстановления"),
                       ("extra_building_slots", "Количество доп. построек")):
        if data.get(key) not in (None, "") and (_num(data.get(key)) is None or _num(data.get(key)) < 0):
            errors.append(f"{label}: неотрицательное число.")

    # Специальные комнаты (§6.3).
    for i, room in enumerate(data.get("special_rooms") or [], start=1):
        if not isinstance(room, dict):
            continue
        rtype = str(room.get("room_type") or "").strip()
        if rtype and rtype not in SPECIAL_ROOM_TYPES:
            warnings.append(f"Комната #{i}: тип «{rtype}» не из списка.")
        if room.get("chance_percent") not in (None, ""):
            ch = _num(room.get("chance_percent"))
            if ch is None or not (0 <= ch <= 100):
                errors.append(f"Комната #{i}: шанс должен быть 0–100.")
        for fkey, flabel in (("time_minutes", "время"), ("daily_limit", "лимит в день"),
                             ("cost", "стоимость")):
            if room.get(fkey) not in (None, "") and (_num(room.get(fkey)) is None or _num(room.get(fkey)) < 0):
                errors.append(f"Комната #{i}: {flabel} — неотрицательное число.")
        for stat in (room.get("stats") or []):
            s = str(stat or "").strip()
            if s and s not in STAT_KEYS:
                warnings.append(f"Комната #{i}: характеристика «{s}» не из списка.")

    # Неулучшаемые постройки (§6.2).
    for i, b in enumerate(data.get("fixed_buildings") or [], start=1):
        if isinstance(b, dict):
            bt = str(b.get("building_type") or "").strip()
            if bt and bt not in FIXED_BUILDINGS:
                warnings.append(f"Постройка #{i}: «{bt}» не из списка неулучшаемых.")

    # Улучшаемые постройки (§6.4).
    for i, b in enumerate(data.get("upgradable_buildings") or [], start=1):
        if not isinstance(b, dict):
            continue
        bt = str(b.get("building_type") or "").strip()
        if bt and bt not in UPGRADABLE_BUILDINGS:
            warnings.append(f"Улучшаемая постройка #{i}: «{bt}» не из списка.")
        for fkey, flabel in (("level", "уровень"), ("max_level", "макс. уровень"),
                             ("upgrade_cost", "стоимость улучшения"),
                             ("upgrade_time_seconds", "время улучшения")):
            if b.get(fkey) not in (None, "") and (_num(b.get(fkey)) is None or _num(b.get(fkey)) < 0):
                errors.append(f"Улучшаемая постройка #{i}: {flabel} — неотрицательное число.")
        lvl = _num(b.get("level"))
        mlvl = _num(b.get("max_level"))
        if lvl is not None and mlvl is not None and lvl > mlvl:
            warnings.append(f"Улучшаемая постройка #{i}: уровень больше максимального.")

    # Домашняя готовка (§6.5).
    for i, dish in enumerate(data.get("dishes") or [], start=1):
        if not isinstance(dish, dict):
            continue
        if not str(dish.get("name") or "").strip():
            errors.append(f"Блюдо #{i}: не заполнено название.")
        dtype = str(dish.get("dish_type") or "").strip()
        if dtype and dtype not in DISH_TYPES:
            warnings.append(f"Блюдо #{i}: тип «{dtype}» не из списка.")
        if dish.get("success_chance") not in (None, ""):
            ch = _num(dish.get("success_chance"))
            if ch is None or not (0 <= ch <= 100):
                errors.append(f"Блюдо #{i}: шанс успеха должен быть 0–100.")
        for fkey, flabel in (("cook_time_seconds", "время приготовления"),
                             ("effect_duration_seconds", "длительность эффекта")):
            if dish.get(fkey) not in (None, "") and (_num(dish.get(fkey)) is None or _num(dish.get(fkey)) < 0):
                errors.append(f"Блюдо #{i}: {flabel} — неотрицательное число.")

    # Отдых дома (§6.6) — восстановление в процентах.
    for key, label in (("restore_hp_percent", "Восстановление HP"),
                       ("restore_mana_percent", "Восстановление маны"),
                       ("restore_spirit_percent", "Восстановление духа"),
                       ("restore_energy_percent", "Восстановление энергии")):
        if data.get(key) not in (None, ""):
            num = _num(data.get(key))
            if num is None or not (0 <= num <= 100):
                errors.append(f"{label}: должно быть 0–100.")

    # Тексты без HTML.
    for key in ("name", "description"):
        if _has_html(data.get(key)):
            errors.append(f"В поле «{key}» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def preview(data: dict[str, Any]) -> dict[str, Any]:
    """Предпросмотр плана жилья (§6)."""
    data = data or {}
    rooms = []
    for r in (data.get("special_rooms") or []):
        if isinstance(r, dict):
            rooms.append({
                "room": SPECIAL_ROOM_LABELS.get(str(r.get("room_type") or ""), str(r.get("room_type") or "—")),
                "stats": [STAT_LABELS.get(str(s), str(s)) for s in (r.get("stats") or [])],
                "chance_percent": r.get("chance_percent"),
                "time_minutes": r.get("time_minutes"),
            })
    dishes = []
    for d in (data.get("dishes") or []):
        if isinstance(d, dict) and str(d.get("name") or "").strip():
            dishes.append({"name": d.get("name"), "dish_type": DISH_TYPE_LABELS.get(str(d.get("dish_type") or ""), str(d.get("dish_type") or ""))})
    return {
        "name": data.get("name") or "Дом игрока",
        "plot_type": PLOT_TYPE_LABELS.get(str(data.get("plot_type") or ""), str(data.get("plot_type") or "—")),
        "house_type": HOUSE_TYPE_LABELS.get(str(data.get("house_type") or ""), str(data.get("house_type") or "—")),
        "cooking_tier": COOKING_TIER_LABELS.get(str(data.get("cooking_tier") or ""), str(data.get("cooking_tier") or "—")),
        "full_rest_minutes": data.get("full_rest_minutes"),
        "special_rooms": rooms,
        "dishes": dishes,
        "extra_building_slots": data.get("extra_building_slots"),
    }
