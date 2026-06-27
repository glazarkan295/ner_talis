"""Конструктор боевых настроек: таймер хода и порядок действий (ТЗ 20 §1–§4, §10).

Запись = профиль боевых настроек для определённой области (глобально / PVE / PVP
/ конкретный моб / событие / подлокация / данж / мировой босс / режим PVP / особый
бой). Управляет таймером хода (по умолчанию 100 с в групповых боях; одиночный PVE
без таймера, кроме исключений) и порядком действий союзников/противников.

Авторский слой: рантайм боя читает эти профили — на вырост. EntityStore
(data/combat_constructor.json).
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403

_HTML_RE = re.compile(r"<[^>]+>")
DEFAULT_TURN_SECONDS = 100

# Область применения профиля (§1.3).
SCOPES = (
    "global", "pve", "pvp", "mob", "event", "sublocation", "dungeon",
    "world_boss", "pvp_mode", "duel", "arena", "special",
)
SCOPE_LABELS = {
    "global": "Глобально (все групповые бои)", "pve": "PVE", "pvp": "PVP",
    "mob": "Конкретный моб", "event": "Событие", "sublocation": "Подлокация",
    "dungeon": "Данж", "world_boss": "Мировой босс", "pvp_mode": "Режим PVP",
    "duel": "Дуэль", "arena": "Арена", "special": "Особый бой",
}
# Действие при истечении таймера (§2.1).
TIMEOUT_ACTIONS = (
    "skip", "defend", "random_attack", "preset_action", "repeat_last",
    "auto", "pass_to_next", "penalty", "kick", "end_battle",
)
TIMEOUT_ACTION_LABELS = {
    "skip": "Пропустить ход", "defend": "Базовая защита",
    "random_attack": "Удар по случайной цели", "preset_action": "Заранее выбранное действие",
    "repeat_last": "Повторить последнее", "auto": "Авто-режим",
    "pass_to_next": "Передать ход следующему", "penalty": "Применить штраф",
    "kick": "Вывести из боя", "end_battle": "Завершить бой",
}
# Порядок союзников-NPC (§3.2).
ALLY_ORDER_TYPES = (
    "player_first", "npc_first", "by_initiative", "by_speed", "by_role",
    "fixed", "random_each_round", "npc_auto_after", "npc_auto_before",
)
# Порядок игроков-союзников (§3.3).
PLAYER_ORDER_TYPES = (
    "sequential", "by_initiative", "by_speed", "simultaneous",
    "leader_choice", "random_each_round", "by_join_order",
)
# Смешанный порядок NPC+игроки (§3.4).
MIXED_ORDER_TYPES = (
    "all_by_initiative", "players_then_npc", "npc_then_players",
    "npc_after_owner", "npc_end_of_round", "npc_start_of_round",
    "npc_between_players", "npc_commander",
)
# Порядок/цели противников (§4).
ENEMY_ORDER_TYPES = ("by_initiative", "before_players", "after_players", "all", "part")
ENEMY_TARGET_RULES = ("random", "aggro", "weakest", "most_dangerous")

_store = EntityStore(
    env_var="COMBAT_CONSTRUCTOR_PATH",
    default_rel="data/combat_constructor.json",
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
        errors.append("Не заполнено название профиля боя.")
    scope = str(data.get("scope") or "").strip()
    if not scope:
        errors.append("Не выбрана область применения (scope).")
    elif scope not in SCOPES:
        errors.append(f"Неизвестная область применения: {scope}.")

    turn = _num(data.get("turn_seconds"))
    if data.get("timer_enabled"):
        if turn is None or turn <= 0:
            errors.append("Таймер включён, но время на ход не задано (turn_seconds).")
        warn = _num(data.get("warn_before_seconds"))
        if warn is not None and turn is not None and warn > turn:
            errors.append("Предупреждение не может быть позже самого таймера.")
    elif turn is not None and turn < 0:
        errors.append("Время на ход не может быть отрицательным.")

    on_timeout = str(data.get("on_timeout") or "").strip()
    if on_timeout and on_timeout not in TIMEOUT_ACTIONS:
        errors.append(f"Неизвестное действие при истечении времени: {on_timeout}.")

    for key, allowed, label in (
        ("ally_order_type", ALLY_ORDER_TYPES, "Порядок союзников-NPC"),
        ("player_order_type", PLAYER_ORDER_TYPES, "Порядок игроков"),
        ("mixed_order_type", MIXED_ORDER_TYPES, "Смешанный порядок"),
        ("enemy_order_type", ENEMY_ORDER_TYPES, "Порядок противников"),
        ("enemy_target_rule", ENEMY_TARGET_RULES, "Выбор цели противников"),
    ):
        val = str(data.get(key) or "").strip()
        if val and val not in allowed:
            warnings.append(f"{label}: значение «{val}» не из списка.")

    for key, label in (("max_players", "Лимит игроков"), ("max_npc", "Лимит NPC"),
                       ("max_extensions", "Макс. продлений")):
        if data.get(key) not in (None, ""):
            num = _num(data.get(key))
            if num is None or num < 0:
                errors.append(f"{label}: неотрицательное число.")

    # §14: групповой бой без таймера / одиночный PVE с таймером без причины.
    if data.get("only_group_battles") and not data.get("timer_enabled"):
        warnings.append("Профиль только для групповых боёв, но таймер хода выключен (ТЗ §14).")
    if data.get("apply_single_pve") and data.get("timer_enabled") and scope in ("pve", "global"):
        warnings.append("Таймер применяется и в одиночном PVE — проверьте, что это осознанно (ТЗ §1.2).")

    for key in ("name", "description", "warn_text", "skip_text"):
        if _has_html(data.get(key)):
            errors.append(f"В поле «{key}» недопустим HTML.")
    for row in (data.get("texts") or []):
        if isinstance(row, dict) and _has_html(row.get("text")):
            errors.append("В тексте сообщения боя недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
