"""Конструктор будущего PVP (ТЗ 4 §1).

Запись = правило/пресет PVP: тип боя (дуэль/арена/осада/…), где разрешён,
условия входа, кнопки боя, награды/штрафы, посмертные проклятья и тексты
игроку. Это АВТОРСКИЙ слой: PVP в игре пока нет, рантайм — на вырост; админ-
панель заранее хранит настройки, чтобы не переписывать систему боя вручную.

Хранение — EntityStore (data/pvp_constructor.json). Чистый слой данных +
валидация + предпросмотр сообщений (TG/VK).
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")

# Типы PVP (§1.3).
PVP_TYPES = (
    "duel", "free", "pvp_zone", "arena", "group", "siege",
    "raid", "contract", "revenge", "event", "tournament",
)
PVP_TYPE_LABELS = {
    "duel": "Дуэль", "free": "Свободный PVP", "pvp_zone": "PVP-зона",
    "arena": "Арена", "group": "Групповой бой", "siege": "Осада",
    "raid": "Рейдовый PVP", "contract": "Заказ на игрока", "revenge": "Месть",
    "event": "Событийный PVP", "tournament": "Турнирный PVP",
}
# Кнопки PVP-боя (§1.5).
PVP_BUTTON_ACTIONS = (
    "attack", "skills", "use_item", "pouch", "defend", "flee", "surrender", "enemy_info",
)
PVP_BUTTON_LABELS = {
    "attack": "Атаковать", "skills": "Навыки", "use_item": "Использовать предмет",
    "pouch": "Подсумок", "defend": "Защита", "flee": "Сбежать",
    "surrender": "Сдаться", "enemy_info": "Информация о противнике",
}
# Единый блок условий (§1.4).
CONDITION_TYPES = (
    "min_level", "max_level_diff", "allowed_location", "forbidden_location",
    "world_event", "active_fine", "no_newbie_protection", "no_pvp_cooldown",
    "has_item", "has_status", "in_event", "in_contract",
)
# Ключи текстов игроку (§1.7) — для предпросмотра/подсказок.
TEXT_KEYS = (
    "invite", "confirm", "decline", "turn_player", "turn_enemy",
    "victory", "defeat", "death", "curse", "reward", "penalty",
)

_store = EntityStore(
    env_var="PVP_CONSTRUCTOR_PATH",
    default_rel="data/pvp_constructor.json",
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
        errors.append("Не заполнено название PVP-правила.")

    pvp_type = str(data.get("pvp_type") or "").strip()
    if not pvp_type:
        errors.append("Не выбран тип PVP.")
    elif pvp_type not in PVP_TYPES:
        errors.append(f"Неизвестный тип PVP: {pvp_type}.")

    # Неотрицательные числовые ограничения.
    for key, label in (("min_level", "Минимальный уровень"),
                       ("max_level_diff", "Макс. разница уровней"),
                       ("cooldown_seconds", "Кулдаун (сек)")):
        if data.get(key) not in (None, ""):
            num = _num(data.get(key))
            if num is None:
                errors.append(f"{label}: не число.")
            elif num < 0:
                errors.append(f"{label}: не может быть отрицательным.")

    # Согласие/дуэль.
    accept = data.get("accept_seconds")
    if accept not in (None, "") and (_num(accept) is None or _num(accept) < 0):
        errors.append("Время на принятие боя — неотрицательное число.")

    # Посмертные проклятья (§1.6).
    if data.get("postdeath_curse_enabled"):
        chance = _num(data.get("postdeath_curse_chance"))
        if chance is None or not (0 <= chance <= 100):
            errors.append("Шанс посмертного проклятья должен быть 0–100.")
        if not (data.get("postdeath_curses") or []):
            warnings.append("Посмертные проклятья включены, но список проклятий пуст.")

    # Кнопки боя (§1.5).
    for i, btn in enumerate(data.get("buttons") or [], start=1):
        if not isinstance(btn, dict):
            continue
        action = str(btn.get("action") or "").strip()
        if action and action not in PVP_BUTTON_ACTIONS:
            warnings.append(f"Кнопка {i}: действие «{action}» не из набора PVP-кнопок.")
        cost = btn.get("resource_cost")
        if cost not in (None, "") and (_num(cost) is None or _num(cost) < 0):
            errors.append(f"Кнопка {i}: расход ресурса — неотрицательное число.")

    # Условия (§1.4).
    for i, cond in enumerate(data.get("conditions") or [], start=1):
        if isinstance(cond, dict):
            ctype = str(cond.get("type") or "").strip()
            if ctype and ctype not in CONDITION_TYPES:
                warnings.append(f"Условие {i}: тип «{ctype}» не из списка.")

    # Тексты игроку: без HTML, плюс предупреждение про §1.6 достижение.
    for key in ("name", "description"):
        if _has_html(data.get(key)):
            errors.append(f"В поле «{key}» недопустим HTML.")
    for row in (data.get("texts") or []):
        if isinstance(row, dict) and _has_html(row.get("text")):
            errors.append("В тексте сообщения недопустим HTML.")

    if pvp_type in ("free", "arena", "duel", "contract", "revenge") and data.get("postdeath_curse_enabled"):
        warnings.append("Посмертные PVP-проклятья учитываются достижением «Проклятье? Какое проклятье?» (только PVP-смерть, ТЗ §1.6).")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def _texts_map(data: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in (data.get("texts") or []):
        if isinstance(row, dict):
            k = str(row.get("key") or "").strip()
            if k:
                out[k] = str(row.get("text") or "")
    return out


def preview(data: dict[str, Any]) -> dict[str, Any]:
    """Предпросмотр ключевых сообщений PVP для TG/VK (§1.7)."""
    data = data or {}
    texts = _texts_map(data)
    type_label = PVP_TYPE_LABELS.get(str(data.get("pvp_type") or ""), str(data.get("pvp_type") or "—"))
    buttons = [
        (str(b.get("text") or PVP_BUTTON_LABELS.get(str(b.get("action") or ""), "")))
        for b in (data.get("buttons") or []) if isinstance(b, dict)
    ]
    buttons = [b for b in buttons if b]
    steps = []
    for key, title in (("invite", "Приглашение"), ("confirm", "Подтверждение"),
                       ("turn_player", "Ход игрока"), ("victory", "Победа"),
                       ("defeat", "Поражение"), ("death", "Смерть"),
                       ("curse", "Посмертное проклятье"), ("reward", "Награда")):
        if texts.get(key):
            steps.append({"step": title, "text": texts[key]})
    return {
        "pvp_type": type_label,
        "enabled": bool(data.get("enabled")),
        "buttons": buttons,
        "steps": steps,
        "postdeath_curse": bool(data.get("postdeath_curse_enabled")),
    }
