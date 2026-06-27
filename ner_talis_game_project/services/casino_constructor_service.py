"""Конструктор «Подпольное казино» (ТЗ 21 §4).

Запись = конфигурация подпольного казино: общие настройки, набор игр (Кости,
Напёрстки, Карты «Очко», Колесо Удачи) с балансом и призами колеса.

Главные правила баланса (§4.1/§4.4):
* казино не должно быть стабильным заработком — шанс проигрыша немного выше шанса
  выигрыша;
* чем выше коэффициент выигрыша, тем ниже шанс победы.

Колесо Удачи (§4.8): от 5 до 10 призов + пустой результат. Особое правило: при
выпадении приза шанс пустого результата повышается на освободившиеся проценты, у
остальных призов шансы не меняются (см. wheel_redistribute).

Хранение — EntityStore (data/casino_constructor.json). Слой данных + валидация +
предпросмотр + чистые хелперы баланса/колеса.
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")

# Игры казино (§4.2).
GAME_TYPES = ("dice", "thimbles", "blackjack", "wheel")
GAME_TYPE_LABELS = {
    "dice": "Кости", "thimbles": "Напёрстки",
    "blackjack": "Карты «Очко»", "wheel": "Колесо Удачи",
}
# Типы призов колеса (§4.8).
WHEEL_PRIZE_TYPES = ("coins", "item", "ingredient", "empty")
WHEEL_PRIZE_LABELS = {
    "coins": "Монеты", "item": "Предмет", "ingredient": "Ингредиент", "empty": "Пусто",
}
CURRENCIES = ("copper", "silver", "gold", "magic_gold", "ancient_coin")

WHEEL_MIN_PRIZES = 5
WHEEL_MAX_PRIZES = 10

_store = EntityStore(
    env_var="CASINO_CONSTRUCTOR_PATH",
    default_rel="data/casino_constructor.json",
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


def wheel_redistribute(prizes: list[dict[str, Any]], empty_chance: Any, won_index: int) -> dict[str, Any]:
    """Особое правило колеса (§4.8): при выпадении приза его шанс освобождается и
    добавляется к шансу пустого результата; шансы остальных призов не меняются.

    Возвращает {"prizes": [...], "empty_chance": float}. Если won_index вне
    диапазона или приз уже пуст — возвращает вход без изменений.
    """
    out = [dict(p) for p in (prizes or [])]
    empty = _num(empty_chance) or 0.0
    if not (0 <= won_index < len(out)):
        return {"prizes": out, "empty_chance": empty}
    freed = _num(out[won_index].get("chance")) or 0.0
    out[won_index]["chance"] = 0
    empty += freed
    return {"prizes": out, "empty_chance": empty}


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not str(data.get("name") or "").strip():
        errors.append("Не заполнено название казино.")
    if not str(data.get("location_id") or "").strip() and not str(data.get("city_id") or "").strip():
        warnings.append("Казино не привязано к локации или городу.")

    # Общие числовые настройки (§4.3).
    for key, label in (("min_level", "Минимальный уровень"),
                       ("min_bet", "Минимальная ставка"),
                       ("max_bet", "Максимальная ставка"),
                       ("games_per_day", "Лимит игр в день"),
                       ("win_per_day", "Лимит выигрыша в день"),
                       ("cooldown_seconds", "Кулдаун"),
                       ("raid_risk_percent", "Риск облавы")):
        if data.get(key) not in (None, ""):
            num = _num(data.get(key))
            if num is None or num < 0:
                errors.append(f"{label}: неотрицательное число.")
    if data.get("raid_risk_percent") not in (None, "") and (_num(data.get("raid_risk_percent")) or 0) > 100:
        errors.append("Риск облавы: должно быть 0–100.")
    bmin = _num(data.get("min_bet"))
    bmax = _num(data.get("max_bet"))
    if bmin is not None and bmax is not None and bmin > bmax:
        errors.append("Минимальная ставка не может быть больше максимальной.")

    # Баланс игр (§4.4). Собираем (coefficient, win_chance) для кросс-проверки.
    coef_points: list[tuple[float, float, int]] = []
    for i, game in enumerate(data.get("games") or [], start=1):
        if not isinstance(game, dict):
            continue
        gtype = str(game.get("game_type") or "").strip()
        if gtype and gtype not in GAME_TYPES:
            warnings.append(f"Игра #{i}: тип «{gtype}» не из списка.")
        win = _num(game.get("win_chance"))
        loss = _num(game.get("loss_chance"))
        for fkey, flabel, val in (("win_chance", "шанс выигрыша", win),
                                  ("loss_chance", "шанс проигрыша", loss)):
            if game.get(fkey) not in (None, "") and (val is None or not (0 <= val <= 100)):
                errors.append(f"Игра #{i}: {flabel} должен быть 0–100.")
        # Шанс проигрыша должен быть немного выше шанса выигрыша (§4.1).
        if win is not None and loss is not None and 0 <= win <= 100 and 0 <= loss <= 100 and loss <= win:
            errors.append(f"Игра #{i}: шанс проигрыша должен быть выше шанса выигрыша (казино — не стабильный заработок).")
        coef = _num(game.get("coefficient"))
        if game.get("coefficient") not in (None, "") and (coef is None or coef < 0):
            errors.append(f"Игра #{i}: коэффициент — неотрицательное число.")
        if coef is not None and win is not None:
            coef_points.append((coef, win, i))
        for fkey, flabel in (("commission", "комиссия"),
                             ("min_loss_chance", "мин. шанс проигрыша"),
                             ("max_win_chance", "макс. шанс выигрыша")):
            if game.get(fkey) not in (None, ""):
                v = _num(game.get(fkey))
                if v is None or not (0 <= v <= 100):
                    errors.append(f"Игра #{i}: {flabel} должно быть 0–100.")

    # Чем выше коэффициент, тем ниже шанс победы (§4.4).
    for a in range(len(coef_points)):
        for b in range(len(coef_points)):
            ca, wa, ia = coef_points[a]
            cb, wb, ib = coef_points[b]
            if ca > cb and wa > wb:
                warnings.append(
                    f"Игра #{ia}: коэффициент выше, чем у игры #{ib}, но и шанс победы выше — "
                    f"нарушает правило «выше коэффициент → ниже шанс победы»."
                )

    # Колесо Удачи (§4.8).
    prizes = data.get("wheel_prizes") or []
    wheel_enabled = bool(data.get("wheel_enabled")) or bool(prizes)
    if wheel_enabled:
        # Считаем призы без учёта служебной строки «пусто».
        real_prizes = [p for p in prizes if isinstance(p, dict)]
        n = len(real_prizes)
        if n < WHEEL_MIN_PRIZES or n > WHEEL_MAX_PRIZES:
            errors.append(f"Колесо Удачи: должно быть от {WHEEL_MIN_PRIZES} до {WHEEL_MAX_PRIZES} призов (сейчас {n}).")
        chance_sum = 0.0
        for i, p in enumerate(real_prizes, start=1):
            ptype = str(p.get("prize_type") or "").strip()
            if ptype and ptype not in WHEEL_PRIZE_TYPES:
                warnings.append(f"Колесо: приз #{i} — тип «{ptype}» не из списка.")
            ch = _num(p.get("chance"))
            if p.get("chance") not in (None, ""):
                if ch is None or not (0 <= ch <= 100):
                    errors.append(f"Колесо: приз #{i} — шанс должен быть 0–100.")
                else:
                    chance_sum += ch
        empty_chance = _num(data.get("wheel_empty_chance")) or 0.0
        if data.get("wheel_empty_chance") not in (None, "") and not (0 <= empty_chance <= 100):
            errors.append("Колесо: шанс пустого результата должен быть 0–100.")
        if chance_sum + empty_chance > 100.0001:
            errors.append(f"Колесо: суммарный шанс призов и пустого результата больше 100% ({chance_sum + empty_chance:g}).")
        if data.get("wheel_spin_cost") not in (None, "") and (_num(data.get("wheel_spin_cost")) is None or _num(data.get("wheel_spin_cost")) < 0):
            errors.append("Колесо: стоимость прокрутки — неотрицательное число.")

    # Тексты без HTML.
    for key in ("name", "description"):
        if _has_html(data.get(key)):
            errors.append(f"В поле «{key}» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def preview(data: dict[str, Any]) -> dict[str, Any]:
    """Предпросмотр казино для игрока (§4)."""
    data = data or {}
    games = []
    for g in (data.get("games") or []):
        if isinstance(g, dict):
            games.append({
                "game_type": GAME_TYPE_LABELS.get(str(g.get("game_type") or ""), str(g.get("game_type") or "—")),
                "coefficient": g.get("coefficient"),
            })
    prizes = []
    for p in (data.get("wheel_prizes") or []):
        if isinstance(p, dict):
            prizes.append({
                "name": p.get("name") or WHEEL_PRIZE_LABELS.get(str(p.get("prize_type") or ""), "—"),
                "chance": (p.get("chance") if data.get("wheel_show_chances") else None),
            })
    return {
        "name": data.get("name") or "Подпольное казино",
        "enabled": bool(data.get("enabled")),
        "games": games,
        "min_bet": data.get("min_bet"),
        "max_bet": data.get("max_bet"),
        "wheel_enabled": bool(data.get("wheel_enabled")) or bool(prizes),
        "wheel_prizes": (prizes if data.get("wheel_show_prizes") else []),
        "wheel_empty_chance": (data.get("wheel_empty_chance") if data.get("wheel_show_chances") else None),
    }
