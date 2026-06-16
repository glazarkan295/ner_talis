"""Боевой стимулятор: откатный дебафф и накопительная «Зависимость».

Активный бафф (+30% урона навыков, +20% к максимуму духа и маны на 30 минут)
по-прежнему обрабатывается боевым движком через запись эффекта
``effect_battle_stimulant``. Этот модуль добавляет то, чего раньше не было:

* откат на 2 часа после окончания действия: −10% точности, уклонения и
  максимума духа/маны/энергии;
* постоянную «Зависимость» (+1 за каждое применение). С 50 единиц появляются
  её дебафы; каждая единица сверх 50 усиливает их примерно на 0.02%;
* пока стимулятор активен, «Зависимость» заблокирована и её дебафы не работают.

Проценты применяются к итоговым производным характеристикам, поэтому механика
видна и в профиле на сайте, и в бою (оба используют derived_stats_service).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

ACTIVE_DURATION_SECONDS = 1800          # 30 минут действия
WITHDRAWAL_DURATION_SECONDS = 7200      # 2 часа отката после действия
ADDICTION_THRESHOLD = 50                # с этого уровня появляются дебафы
ADDICTION_BASE_PERCENT = 0.5            # величина дебафа на пороге
ADDICTION_STEP_PERCENT = 0.02           # прирост за каждую единицу сверх порога

# Откатные дебафы (в процентах от итоговой характеристики).
WITHDRAWAL_PERCENT = 10

# Ключи производных характеристик, на которые влияет механика.
WITHDRAWAL_NEGATIVE_KEYS = ("accuracy", "dodge", "max_spirit", "max_mana", "max_energy")

# Знак дебафа «Зависимости» по характеристикам: отрицательные ухудшают,
# положительные (урон/крит. урон) — обратная сторона привыкания.
ADDICTION_STAT_SIGNS = {
    "dodge": -1,
    "accuracy": -1,
    "crit_chance_percent": -1,
    "max_hp": -1,
    "skill_damage": +1,
    "crit_damage_percent": +1,
}


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def addiction_level(player: dict[str, Any]) -> int:
    data = player.get("battle_stimulant_addiction")
    if isinstance(data, dict):
        return max(0, _safe_int(data.get("level"), 0))
    return max(0, _safe_int(data, 0))


def register_battle_stimulant_use(player: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Фиксирует применение: продлевает действие, ставит откат, растит зависимость."""

    now = _now(now)
    active_until = now + timedelta(seconds=ACTIVE_DURATION_SECONDS)
    withdrawal_until = active_until + timedelta(seconds=WITHDRAWAL_DURATION_SECONDS)
    player["battle_stimulant_active_until"] = active_until.isoformat()
    player["battle_stimulant_withdrawal_until"] = withdrawal_until.isoformat()

    addiction = player.get("battle_stimulant_addiction")
    if not isinstance(addiction, dict):
        addiction = {"level": _safe_int(addiction, 0)}
        player["battle_stimulant_addiction"] = addiction
    addiction["level"] = max(0, _safe_int(addiction.get("level"), 0)) + 1
    return {
        "active_until": player["battle_stimulant_active_until"],
        "withdrawal_until": player["battle_stimulant_withdrawal_until"],
        "addiction_level": addiction["level"],
    }


def battle_stimulant_phase(player: dict[str, Any], now: datetime | None = None) -> str:
    """Возвращает 'active' | 'withdrawal' | 'none'."""

    now = _now(now)
    active_until = _parse_dt(player.get("battle_stimulant_active_until"))
    if active_until and now < active_until:
        return "active"
    withdrawal_until = _parse_dt(player.get("battle_stimulant_withdrawal_until"))
    if withdrawal_until and now < withdrawal_until:
        return "withdrawal"
    return "none"


def _addiction_magnitude_percent(level: int) -> float:
    if level < ADDICTION_THRESHOLD:
        return 0.0
    return ADDICTION_BASE_PERCENT + ADDICTION_STEP_PERCENT * (level - ADDICTION_THRESHOLD)


def stat_percent_modifiers(player: dict[str, Any], now: datetime | None = None) -> dict[str, float]:
    """Суммарные процентные модификаторы по характеристикам (+ skill_damage)."""

    phase = battle_stimulant_phase(player, now)
    percents: dict[str, float] = {}

    if phase == "withdrawal":
        for key in WITHDRAWAL_NEGATIVE_KEYS:
            percents[key] = percents.get(key, 0.0) - WITHDRAWAL_PERCENT

    # «Зависимость» работает в любой фазе, кроме активной (тогда заблокирована).
    if phase != "active":
        magnitude = _addiction_magnitude_percent(addiction_level(player))
        if magnitude > 0:
            for key, sign in ADDICTION_STAT_SIGNS.items():
                percents[key] = percents.get(key, 0.0) + sign * magnitude

    return percents


def skill_damage_multiplier(player: dict[str, Any], now: datetime | None = None) -> float:
    """Множитель урона навыков от «Зависимости» (активный +30% считается отдельно)."""

    percent = stat_percent_modifiers(player, now).get("skill_damage", 0.0)
    return max(0.0, 1.0 + percent / 100.0)


def apply_percent_modifiers_to_stats(player: dict[str, Any], stats: dict[str, Any], now: datetime | None = None) -> None:
    """Накладывает процентные модификаторы на уже посчитанные производные статы."""

    percents = stat_percent_modifiers(player, now)
    if not percents:
        return
    floors = {
        "max_hp": 1,
        "max_spirit": 0,
        "max_mana": 0,
        "max_energy": 1,
        "accuracy": 1,
        "dodge": 1,
        "crit_chance_percent": 0,
        "crit_damage_percent": 100,
    }
    for key, percent in percents.items():
        if key == "skill_damage" or key not in stats:
            continue
        base = stats.get(key)
        if not isinstance(base, (int, float)):
            continue
        adjusted = float(base) * (1.0 + percent / 100.0)
        floor = floors.get(key, 0)
        stats[key] = max(floor, int(round(adjusted)))
    # current_energy не может превышать обновлённый максимум.
    if "max_energy" in stats and "current_energy" in stats:
        stats["current_energy"] = max(0, min(_safe_int(stats.get("current_energy"), 0), _safe_int(stats.get("max_energy"), 0)))


def battle_stimulant_status_effect(player: dict[str, Any], now: datetime | None = None) -> dict[str, Any] | None:
    """Карточка для раздела «Эффекты» в профиле: откат или зависимость."""

    phase = battle_stimulant_phase(player, now)
    level = addiction_level(player)
    if phase == "withdrawal":
        description = (
            "Откат после боевого стимулятора: точность, уклонение и максимум "
            "духа, маны и энергии снижены на 10% на 2 часа."
        )
        # Во время отката (фаза не «активна») «Зависимость» тоже действует и
        # меняет статы — показываем её здесь, иначе изменения были бы скрытыми.
        if level >= ADDICTION_THRESHOLD:
            magnitude = _addiction_magnitude_percent(level)
            description += (
                f"\nЗависимость ({level}): уклонение, точность, шанс крита и HP "
                f"снижены на {magnitude:.2f}%, базовый урон и урон крита изменены "
                f"на {magnitude:.2f}%."
            )
        return {
            "id": "effect_battle_stimulant_withdrawal",
            "name": "Откат боевого стимулятора",
            "source": "battle_stimulant_withdrawal",
            "kind": "negative",
            "expires_at": player.get("battle_stimulant_withdrawal_until"),
            "description": description,
        }
    if phase != "active" and level >= ADDICTION_THRESHOLD:
        magnitude = _addiction_magnitude_percent(level)
        return {
            "id": "effect_battle_stimulant_addiction",
            "name": f"Зависимость от стимулятора ({level})",
            "source": "battle_stimulant_addiction",
            "kind": "negative",
            "description": (
                f"Привыкание к боевому стимулятору: уклонение, точность, шанс крита и HP "
                f"снижены на {magnitude:.2f}%, базовый урон и урон крита изменены на "
                f"{magnitude:.2f}%. Пока стимулятор активен, зависимость не действует."
            ),
        }
    return None
