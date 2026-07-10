"""Конструктор NPC-союзников (ТЗ 21 §2).

Запись = шаблон NPC-союзника: помощник игрока/группы, который участвует в бою,
добыче, событиях, сопровождении, защите, ремесле. Хранит карточку характеристик,
способы получения, поведение в бою и правила добычи/прогресса. Это слой данных +
валидация + предпросмотр карточки; рантайм-призыв/найм — на вырост.

Хранение — EntityStore (data/npc_ally_constructor.json).
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")

# Типы союзников (§2.2).
ALLY_TYPES = (
    "combat", "healer", "defender", "scout", "tracker", "porter", "gatherer",
    "craft_helper", "magic_helper", "mercenary", "story_companion",
    "event_ally", "guild_ally", "tavern_mercenary", "house_worker", "guard",
    "summon",
)
ALLY_TYPE_LABELS = {
    "combat": "Боевой союзник", "healer": "Лекарь", "defender": "Защитник",
    "scout": "Разведчик", "tracker": "Следопыт", "porter": "Носильщик",
    "gatherer": "Добытчик", "craft_helper": "Ремесленный помощник",
    "magic_helper": "Магический помощник", "mercenary": "Временный наёмник",
    "story_companion": "Сюжетный спутник", "event_ally": "Событийный союзник",
    "guild_ally": "Гильдейский союзник", "tavern_mercenary": "Таверный наёмник",
    "house_worker": "Домашний работник", "guard": "Охранник",
    "summon": "Призванное существо",
}
# Способы получения (§2.3).
ACQUIRE_METHODS = (
    "hire", "quest", "achievement", "event", "tavern", "guild", "house",
    "item", "skill", "sublocation", "world_event", "admin_grant",
)
ACQUIRE_METHOD_LABELS = {
    "hire": "Нанять за монеты", "quest": "По заданию", "achievement": "За достижение",
    "event": "Через событие", "tavern": "В таверне", "guild": "В гильдии",
    "house": "В доме", "item": "Через предмет", "skill": "Призвать навыком",
    "sublocation": "Временно в подлокации", "world_event": "От мирового события",
    "admin_grant": "Выдать через админ-панель",
}
# Поведение хода в бою (§2.6).
COMBAT_TURN_MODES = (
    "auto", "by_command", "after_player", "before_player", "by_initiative",
)
COMBAT_TURN_LABELS = {
    "auto": "Ходит автоматически", "by_command": "Ходит по команде игрока",
    "after_player": "Ходит после игрока", "before_player": "Ходит до игрока",
    "by_initiative": "Ходит по инициативе",
}
# Кто выбирает цель (§2.6).
TARGET_MODES = ("self", "player", "priority_list")
TARGET_MODE_LABELS = {
    "self": "Союзник выбирает сам", "player": "Цель выбирает игрок",
    "priority_list": "По приоритету целей",
}
# Способности (§2.5) — для подсказок/предпросмотра.
ABILITIES = (
    "attack", "protect_owner", "heal", "cleanse", "buff", "debuff", "taunt",
    "find_resources", "boost_find_chance", "reduce_trap_risk", "detect_passage",
    "carry_loot", "craft", "speed_craft", "help_dialog", "open_events",
    "escort", "defend_home", "pve", "pvp",
)
CURRENCIES = ("copper", "silver", "gold", "magic_gold", "ancient_coin")

# --- ТЗ 2.0 (файл 10 ч.3): углубление NPC-помощников ------------------------
# Способы восстановления после смерти/выбытия (§62).
REVIVAL_METHODS = ("time", "camp", "npc", "quest", "payment", "auto_after_battle")
REVIVAL_METHOD_LABELS = {
    "time": "Через время", "camp": "Через лагерь", "npc": "Через NPC",
    "quest": "Через квест", "payment": "За оплату", "auto_after_battle": "Автоматически после боя",
}
# Разрешение в PVP (§58).
PVP_ALLOW_MODES = (
    "forbidden", "allowed", "duel_only", "criminal_only", "event_only", "mirror_only",
)
PVP_ALLOW_LABELS = {
    "forbidden": "Запрещён в PVP", "allowed": "Разрешён в PVP",
    "duel_only": "Только в дуэлях", "criminal_only": "Только в криминальном PVP",
    "event_only": "Только в эвентах", "mirror_only": "Только если у противника тоже есть помощник",
}
# Внебоевые действия (§59).
OUT_OF_BATTLE_ACTIONS = (
    "find_resources", "reduce_event_risk", "boost_noncombat_event", "reduce_encounter",
    "help_craft", "speed_rest", "help_camp", "open_sublocation", "find_npc",
    "find_player", "carry_items", "hints", "quest_actions",
)

_store = EntityStore(
    env_var="NPC_ALLY_CONSTRUCTOR_PATH",
    default_rel="data/npc_ally_constructor.json",
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
        errors.append("Не заполнено имя NPC-союзника.")

    ally_type = str(data.get("ally_type") or "").strip()
    if not ally_type:
        errors.append("Не выбран тип союзника.")
    elif ally_type not in ALLY_TYPES:
        errors.append(f"Неизвестный тип союзника: {ally_type}.")

    method = str(data.get("acquire_method") or "").strip()
    if method and method not in ACQUIRE_METHODS:
        warnings.append(f"Способ получения «{method}» не из списка.")

    # Неотрицательные числовые поля (стоимость/длительность/лимиты/характеристики).
    for key, label in (
        ("cost", "Стоимость"), ("level", "Уровень"), ("rank", "Ранг"),
        ("hp", "Здоровье"), ("mana", "Мана"), ("spirit", "Дух"),
        ("energy", "Энергия"), ("armor", "Броня"),
        ("phys_defense", "Физическая защита"), ("magic_defense", "Магическая защита"),
        ("speed", "Скорость/инициатива"),
        ("duration_seconds", "Длительность"), ("battles_limit", "Количество боёв/действий"),
        ("time_limit_seconds", "Лимит времени"), ("cooldown_seconds", "Кулдаун"),
        ("required_level", "Требуемый уровень игрока"),
        ("required_reputation", "Требуемая репутация"),
    ):
        if data.get(key) not in (None, ""):
            num = _num(data.get(key))
            if num is None:
                errors.append(f"{label}: не число.")
            elif num < 0:
                errors.append(f"{label}: не может быть отрицательным.")

    # Процентные поля 0–100 (точность/уклонение/крит/доля добычи и т.п.).
    for key, label in (
        ("accuracy", "Точность"), ("dodge", "Уклонение"),
        ("crit_chance", "Критический шанс"),
        ("loot_share_percent", "Доля добычи"),
        ("find_bonus_percent", "Бонус к шансу находки"),
        ("owner_reward_penalty_percent", "Снижение награды игрока"),
    ):
        if data.get(key) not in (None, ""):
            num = _num(data.get(key))
            if num is None or not (0 <= num <= 100):
                errors.append(f"{label}: должно быть 0–100.")
    # Урон крита — множитель, может быть > 100%, но не отрицательный.
    if data.get("crit_damage") not in (None, ""):
        num = _num(data.get("crit_damage"))
        if num is None or num < 0:
            errors.append("Урон крита: неотрицательное число.")

    # Цена > 0 без валюты — предупреждение.
    if (_num(data.get("cost")) or 0) > 0 and not str(data.get("currency") or "").strip():
        warnings.append("Указана стоимость найма, но не выбрана валюта.")

    # Поведение в бою (§2.6).
    turn_mode = str(data.get("combat_turn_mode") or "").strip()
    if turn_mode and turn_mode not in COMBAT_TURN_MODES:
        warnings.append(f"Поведение хода «{turn_mode}» не из списка.")
    target_mode = str(data.get("target_mode") or "").strip()
    if target_mode and target_mode not in TARGET_MODES:
        warnings.append(f"Режим выбора цели «{target_mode}» не из списка.")
    # Воскрешение возможно только если союзник может погибнуть.
    if data.get("can_revive") and not data.get("can_die"):
        warnings.append("«Можно воскресить» включено, но союзник не может погибнуть.")

    # Способности (§2.5).
    for ability in (data.get("abilities") or []):
        a = str(ability or "").strip()
        if a and a not in ABILITIES:
            warnings.append(f"Способность «{a}» не из списка.")

    # --- ТЗ 2.0 (файл 10 ч.3) ---
    # Лояльность (§61): start в пределах [min, max], значения ≥ 0.
    if data.get("loyalty_enabled"):
        lmin = _num(data.get("loyalty_min"))
        lmax = _num(data.get("loyalty_max"))
        lstart = _num(data.get("loyalty_start"))
        for key, label in (("loyalty_min", "минимальная лояльность"),
                           ("loyalty_max", "максимальная лояльность"),
                           ("loyalty_start", "стартовая лояльность")):
            if data.get(key) not in (None, "") and (_num(data.get(key)) is None or _num(data.get(key)) < 0):
                errors.append(f"Лояльность: {label} — неотрицательное число.")
        if lmin is not None and lmax is not None and lmin > lmax:
            errors.append("Лояльность: минимум больше максимума.")
        if lstart is not None and lmin is not None and lmax is not None and not (lmin <= lstart <= lmax):
            errors.append("Лояльность: стартовое значение вне диапазона [min, max].")

    # Развитие (§60): уровни ≥ 0, текущий ≤ максимального.
    if data.get("has_levels"):
        for key, label in (("dev_level", "текущий уровень"), ("dev_max_level", "максимальный уровень"),
                           ("dev_exp_per_battle", "опыт за бой"), ("dev_exp_per_quest", "опыт за квест")):
            if data.get(key) not in (None, "") and (_num(data.get(key)) is None or _num(data.get(key)) < 0):
                errors.append(f"Развитие: {label} — неотрицательное число.")
        cur, mx = _num(data.get("dev_level")), _num(data.get("dev_max_level"))
        if cur is not None and mx is not None and cur > mx:
            warnings.append("Развитие: текущий уровень больше максимального.")

    # Восстановление (§62).
    for method in (data.get("revival_methods") or []):
        if str(method or "").strip() and str(method).strip() not in REVIVAL_METHODS:
            warnings.append(f"Способ восстановления «{method}» не из списка.")
    if data.get("can_die") and not (data.get("revival_methods") or []) and not data.get("permanent_death"):
        warnings.append("Союзник может погибнуть, но не задан способ восстановления и смерть не помечена как окончательная.")

    # PVP (§58).
    pvp_mode = str(data.get("pvp_allow_mode") or "").strip()
    if pvp_mode and pvp_mode not in PVP_ALLOW_MODES:
        warnings.append(f"Режим допуска в PVP «{pvp_mode}» не из списка.")
    if pvp_mode and pvp_mode != "forbidden" and not (data.get("abilities") or []) and not data.get("hp"):
        warnings.append("Союзник допущен в PVP, но нет боевых параметров/навыков (баланс §66).")

    # Внебоевые действия (§59).
    for act in (data.get("out_of_battle_actions") or []):
        if str(act or "").strip() and str(act).strip() not in OUT_OF_BATTLE_ACTIONS:
            warnings.append(f"Внебоевое действие «{act}» не из списка.")

    # Тексты без HTML.
    for key in ("name", "description", "out_of_battle_behavior"):
        if _has_html(data.get(key)):
            errors.append(f"В поле «{key}» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def preview(data: dict[str, Any]) -> dict[str, Any]:
    """Предпросмотр карточки союзника (§2.4)."""
    data = data or {}
    abilities = [a for a in (data.get("abilities") or []) if str(a or "").strip()]
    return {
        "name": data.get("name") or "—",
        "ally_type": ALLY_TYPE_LABELS.get(str(data.get("ally_type") or ""), str(data.get("ally_type") or "—")),
        "level": data.get("level"),
        "rank": data.get("rank"),
        "stats": {
            "hp": data.get("hp"), "mana": data.get("mana"),
            "spirit": data.get("spirit"), "energy": data.get("energy"),
            "armor": data.get("armor"),
        },
        "acquire": ACQUIRE_METHOD_LABELS.get(str(data.get("acquire_method") or ""), str(data.get("acquire_method") or "—")),
        "cost": data.get("cost"),
        "currency": data.get("currency"),
        "abilities": [a for a in abilities],
        "combat_turn": COMBAT_TURN_LABELS.get(str(data.get("combat_turn_mode") or ""), str(data.get("combat_turn_mode") or "—")),
        "can_die": bool(data.get("can_die")),
        "loot_share_percent": data.get("loot_share_percent"),
    }
