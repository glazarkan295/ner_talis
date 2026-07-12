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
    "achievement": ("live", None, "Опубликованные достижения исполняются achievement_engine; игровые хуки подключены к боям, квестам, ремеслу, рынку, событиям, репутации, штрафам, доставке, рыбалке и казино."),
    "item": ("live", None, "Опубликованные предметы подмешиваются item_constructor_service в item_registry и доступны игровым системам."),
    "effect": ("live", None, "Опубликованные эффекты разрешаются effect_constructor_service и применяются расчётом характеристик/боя."),
    "skill": ("live", None, "Опубликованные навыки перекрывают статический каталог; расход ресурса, урон и усиление по уровню применяют опубликованные формулы."),
    "formula": ("live", None, "Единый AST-whitelist runtime исполняет только published-формулы; подключены бой, опыт/уровни, мобы, эффекты, предметы, дроп, доставка, ремонт, навыки, ремесло, штрафы, экономика и события."),
    "recipe": ("live", "services.crafting_service.load_crafting_recipes", "Опубликованные рецепты перекрывают статические определения по ID."),
    "quest": ("live", None, "Опубликованные задания запускаются quest_runtime_service; прогресс подключён к PVE, PVP и ремеслу."),
    "pvp": ("live", None, "Опубликованные PVP-правила исполняются pvp_runtime_service и игровым PVP API."),
    "economy": ("live", None, "Опубликованные валюты и правила экономики читаются economy_constructor_service; комиссии применяются рынком."),
    "event_campaign": ("live", None, "Опубликованные эвенты исполняются event_campaign_runtime: участие, этапы, задачи, награды и рейтинг; доступны ботам и web API."),
    "broadcast_campaign": ("live", None, "Опубликованные рассылки исполняются пакетным worker: аудитория, расписание, награды, очередь, остановка и журнал."),
    "referral": ("live", None, "Опубликованная реферальная программа задаёт ссылки, награды и ограничения referral_service."),
    "reputation": ("live", None, "Опубликованные правила применяются reputation_runtime_service: игровые триггеры, история, профиль и цены/запрет рынка."),
}


def status_for(key: str) -> dict[str, Any]:
    cat, flag, note = _STATUS.get(key, ("reference", None, ""))
    return {"category": cat, "category_label": CATEGORY_LABELS.get(cat, cat), "flag": flag, "note": note}


def all_statuses() -> dict[str, dict[str, Any]]:
    return {key: status_for(key) for key in _STATUS}
