"""Конструктор боевых настроек: таймер хода и порядок действий (ТЗ 20 §1–§4, §10).

Запись = профиль боевых настроек для определённой области (глобально / PVE / PVP
/ конкретный моб / событие / подлокация / данж / мировой босс / режим PVP / особый
бой). Управляет таймером хода (по умолчанию 100 с в групповых боях; одиночный PVE
без таймера, кроме исключений) и порядком действий союзников/противников.

Опубликованные профили читаются боевым runtime через resolve_profile.
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
PARTICIPANT_TYPES = (
    "player", "player_ally", "player_enemy", "npc_ally", "enemy_npc_ally",
    "mob", "boss", "world_boss", "summon", "clone", "temporary_companion",
    "shadow", "neutral", "third_party",
)
PARTICIPANT_SIDES = (
    "player", "enemy", "pvp_initiator", "pvp_defender", "neutral",
    "third_party", "player_allies", "enemy_allies",
)
ALLY_BEHAVIORS = (
    "nearest", "weakest", "most_dangerous", "protect_player", "heal_allies",
    "buff_allies", "cleanse", "random_skill", "priorities", "player_command", "auto",
)
ALLY_COMMANDS = ("attack", "protect", "heal", "use_skill", "wait", "change_target", "retreat")
PVE_TYPES=("one_on_one","player_vs_mob","player_npc_vs_mobs","player_allies_vs_mobs","mixed_allies_vs_mobs","party_vs_group","raid_boss","world_boss","event_battle","quest_battle","training","service")
PVE_SOURCES=("location_event","hidden_event","button","npc","quest","world_event","event_campaign","zone","item","ambush","raid","transition","camp","admin")
TURN_ORDERS=("fixed","initiative","agility","perception","speed","random","player_first","mob_first","allies_after","allies_before","mobs_sequential","side_simultaneous","participant_separate")
MOB_ESCAPE_CONDITIONS=("hp_percent","hp_value","alone","leader_dead","boss_dead","summoner_dead","allies_dead","rounds","player_damage","level_difference","has_effect","missing_effect","critical_hit","misses","no_damage","objective_done","reinforcement_called","phase","scenario")
MOB_ESCAPE_MODES=("individual","group","scenario","boss_retreat")

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

    participants = [row for row in (data.get("participants") or []) if isinstance(row, dict)]
    seen: set[str] = set()
    for index, row in enumerate(participants, 1):
        pid = str(row.get("participant_id") or "").strip()
        if not pid:
            errors.append(f"Участник {index}: не заполнен ID.")
        elif pid in seen:
            errors.append(f"Участник {index}: ID «{pid}» повторяется.")
        seen.add(pid)
        ptype = str(row.get("participant_type") or "").strip()
        if ptype not in PARTICIPANT_TYPES:
            errors.append(f"Участник {index}: неизвестный тип «{ptype}».")
        side = str(row.get("side") or "").strip()
        if side not in PARTICIPANT_SIDES:
            errors.append(f"Участник {index}: неизвестная сторона «{side}».")
        behavior = str(row.get("behavior") or "").strip()
        if behavior and behavior not in ALLY_BEHAVIORS:
            errors.append(f"Участник {index}: неизвестное поведение «{behavior}».")
        for key in ("hp", "mana", "spirit", "energy", "damage", "order"):
            if row.get(key) not in (None, "") and (_num(row.get(key)) is None or _num(row.get(key)) < 0):
                errors.append(f"Участник {index}: {key} должно быть неотрицательным числом.")
        if ptype in {"npc_ally", "enemy_npc_ally"} and not str(row.get("source_id") or "").strip():
            errors.append(f"Участник {index}: для NPC-союзника нужен source_id.")
    if participants and not any(str(row.get("side")) in {"player", "player_allies", "pvp_initiator"} for row in participants):
        errors.append("В боевой группе нет участника стороны игрока.")
    if participants and not any(str(row.get("side")) in {"enemy", "enemy_allies", "pvp_defender", "third_party"} for row in participants):
        warnings.append("В группе не задан противник; он должен поступить из запускающего моба/PVP-вызова.")

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
    if scope in {"pve","mob","event","sublocation","dungeon","world_boss"}:
        pve_type=str(data.get("pve_type") or "player_vs_mob");source=str(data.get("battle_source") or "location_event");order=str(data.get("turn_order") or "initiative")
        if pve_type not in PVE_TYPES:errors.append(f"Неизвестный тип PVE: {pve_type}.")
        if source not in PVE_SOURCES:errors.append(f"Неизвестный источник PVE: {source}.")
        if order not in TURN_ORDERS:errors.append(f"Неизвестная очерёдность: {order}.")
        if data.get("allow_player_allies") and not str(data.get("afk_action") or ""):warnings.append("Разрешены игроки-союзники, но не задана AFK-логика.")
        for i,row in enumerate(data.get("mob_escape_rules") or [],1):
            if not isinstance(row,dict):errors.append(f"Побег моба #{i}: неверный формат.");continue
            if row.get("enabled") and str(row.get("condition_type") or "") not in MOB_ESCAPE_CONDITIONS:errors.append(f"Побег моба #{i}: не задано условие.")
            if str(row.get("mode") or "individual") not in MOB_ESCAPE_MODES:errors.append(f"Побег моба #{i}: неизвестный режим.")
            chance=_num(row.get("chance"))
            if chance is not None and not 0<=chance<=100:errors.append(f"Побег моба #{i}: шанс должен быть 0–100.")
            if row.get("enabled") and not row.get("success_text"):warnings.append(f"Побег моба #{i}: нет текста успешного побега.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def resolve_profile(scope: str, *, object_id: str = "", group_battle: bool = False) -> dict[str, Any]:
    """Разрешить live-профиль: точный объект → область → global → defaults."""
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for env in store().list(status=STATUS_PUBLISHED):  # noqa: F405
        data = dict(env.get("data") or {})
        current = str(data.get("scope") or "")
        if current not in (scope, "global"):
            continue
        target = str(data.get("scope_id") or data.get("object_id") or "")
        if target and target != object_id:
            continue
        specificity = 2 if target else (1 if current == scope else 0)
        ranked.append((specificity, int(data.get("priority") or 0), data))
    if ranked:
        ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return ranked[0][2]
    return {"scope": scope, "timer_enabled": bool(group_battle), "turn_seconds": DEFAULT_TURN_SECONDS,
            "on_timeout": "skip", "player_order_type": "sequential", "enemy_target_rule": "random"}
