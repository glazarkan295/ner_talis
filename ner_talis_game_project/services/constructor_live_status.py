"""Live-runtime статус конструкторов (16-TZ §9–§11).

Честная карта: какие конструкторы реально влияют на игру, какие пока только
авторский слой/справочник, и какой feature flag/env нужен для live-режима. Цель
— чтобы админ не думал, что опубликованный объект уже в игре, когда runtime ещё
читает legacy-логику.

Категории (§10):
* live      — «Работает в игре» (опубликованный объект сразу используется);
* partial   — «Частично работает в игре»;
* flag      — «Требует включения feature flag» (live только при включённом флаге);
* reference — «Только справочник» (пока не меняет gameplay);
* disabled  — «Отключён/черновик».
"""

from __future__ import annotations

from typing import Any

CATEGORY_LABELS = {
    "live": "Работает в игре",
    "partial": "Частично работает в игре",
    "flag": "Требует включения feature flag",
    "reference": "Только справочник",
    "disabled": "Отключён",
}

# key конструктора → (категория, флаг/none, заметка о runtime).
_STATUS: dict[str, tuple[str, str | None, str]] = {
    "location": ("flag", "use_v2_locations", "Живой слой поиска/боя/лимитов — при WORLD_CONSTRUCTOR_LIVE или флаге use_v2_locations."),
    "event": ("flag", "use_v2_locations", "События локаций идут в игру вместе с живым слоем мира (use_v2_locations)."),
    "mob": ("flag", "use_v2_locations", "Конструкторные мобы в бою — при живом слое мира (use_v2_locations)."),
    "city_node": ("flag", "use_v2_buttons", "Навигация города из конструктора — при CITY_CONSTRUCTOR_LIVE или флаге use_v2_buttons."),
    "text": ("flag", "use_v2_texts", "Тексты бота берутся из конструктора при включённом use_v2_texts (иначе старый код)."),
    "achievement": ("partial", None, "Движок достижений работает (achievement_engine), но авто-хуки расставлены не везде."),
    "item": ("reference", None, "Игра читает предметы из item_registry (data/items_*.json); конструктор — авторский слой."),
    "effect": ("reference", None, "Эффекты в бою пока на legacy-логике; конструктор — справочник/валидация."),
    "recipe": ("reference", None, "Крафт читает data/crafting_recipes.json; конструктор — авторский слой."),
    "reputation": ("reference", None, "Рантайм-применение репутации — на вырост; пока авторский слой."),
}


def status_for(key: str) -> dict[str, Any]:
    cat, flag, note = _STATUS.get(key, ("reference", None, ""))
    return {"category": cat, "category_label": CATEGORY_LABELS.get(cat, cat), "flag": flag, "note": note}


def all_statuses() -> dict[str, dict[str, Any]]:
    return {key: status_for(key) for key in _STATUS}
