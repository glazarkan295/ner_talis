"""Лимиты рангов мобов (ТЗ «черты/благословения/фазы», §2.1–§2.2, §11.5).

Чистый слой данных + валидатор: по рангу моба даёт рекомендованные лимиты на
активные/пассивные навыки, черты (особые/элитные/уникальные/мировые), фазы и
число активных навыков за ход. Валидатор сравнивает фактические количества с
лимитами и возвращает ошибки/предупреждения по режиму проверки.

Сам конструктор мобов и его роутер используют это для автоподстановки лимитов и
предупреждений; здесь нет ни хранилища, ни прав — только правила.
"""

from __future__ import annotations

from typing import Any

RANKS = (
    "normal", "strengthened", "special", "elite", "mini_boss",
    "boss", "raid_boss", "world_boss", "unique",
)

RANK_LABELS = {
    "normal": "Обычный", "strengthened": "Усиленный", "special": "Особый",
    "elite": "Элитный", "mini_boss": "Мини-босс", "boss": "Босс",
    "raid_boss": "Рейдовый босс", "world_boss": "Мировой босс", "unique": "Уникальный",
}

VALIDATION_MODES = ("strict", "warning_only", "manual_override")

# (min, max) по каждому показателю. Для черт min=0 (не обязательны), max — верхний
# предел из таблицы §2.1; для навыков/фаз/действий — границы диапазона.
RANK_LIMITS: dict[str, dict[str, tuple[int, int]]] = {
    "normal":       {"active": (2, 2),  "passive": (0, 0),   "special": (0, 0), "elite": (0, 0), "unique": (0, 0), "world": (0, 0), "phases": (1, 1), "per_turn": (1, 1)},
    "strengthened": {"active": (2, 2),  "passive": (1, 1),   "special": (0, 0), "elite": (0, 0), "unique": (0, 0), "world": (0, 0), "phases": (1, 1), "per_turn": (1, 1)},
    "special":      {"active": (3, 3),  "passive": (1, 1),   "special": (0, 1), "elite": (0, 0), "unique": (0, 0), "world": (0, 0), "phases": (1, 1), "per_turn": (1, 1)},
    "elite":        {"active": (4, 5),  "passive": (2, 3),   "special": (0, 0), "elite": (0, 1), "unique": (0, 0), "world": (0, 0), "phases": (1, 1), "per_turn": (1, 1)},
    "mini_boss":    {"active": (5, 6),  "passive": (4, 4),   "special": (0, 2), "elite": (0, 1), "unique": (0, 0), "world": (0, 0), "phases": (1, 2), "per_turn": (1, 1)},
    "boss":         {"active": (8, 10), "passive": (6, 6),   "special": (0, 3), "elite": (0, 2), "unique": (0, 0), "world": (0, 0), "phases": (2, 3), "per_turn": (1, 2)},
    "raid_boss":    {"active": (15, 20), "passive": (10, 10), "special": (0, 5), "elite": (0, 3), "unique": (0, 0), "world": (0, 0), "phases": (4, 5), "per_turn": (1, 3)},
    "world_boss":   {"active": (20, 30), "passive": (15, 15), "special": (0, 7), "elite": (0, 5), "unique": (0, 0), "world": (0, 1), "phases": (6, 6), "per_turn": (1, 6)},
    "unique":       {"active": (2, 10), "passive": (2, 15),  "special": (0, 4), "elite": (0, 2), "unique": (0, 2), "world": (0, 0), "phases": (2, 3), "per_turn": (1, 2)},
}

# Поле моба → ключ показателя в RANK_LIMITS + русская подпись для сообщений.
_METRICS: tuple[tuple[str, str, str], ...] = (
    ("active_skills", "active", "активных навыков"),
    ("passive_skills", "passive", "пассивных навыков"),
    ("special_traits", "special", "особых черт"),
    ("elite_traits", "elite", "элитных черт"),
    ("unique_traits", "unique", "уникальных черт"),
    ("world_traits", "world", "мировых черт"),
    ("phases", "phases", "фаз"),
)

# Минимум проверяем только для навыков; черты/фазы — необязательные дополнения.
_MIN_ENFORCED = frozenset({"active", "passive"})


def recommended_limits(rank: str) -> dict[str, tuple[int, int]] | None:
    """Рекомендованные (min, max) лимиты для ранга или None для неизвестного."""
    return RANK_LIMITS.get(str(rank or "").strip())


def _count(value: Any) -> int:
    return len(value) if isinstance(value, (list, tuple)) else 0


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def validate_mob_rank_limits(data: dict[str, Any], *, mode: str = "warning_only") -> dict[str, Any]:
    """Сверить количества навыков/черт/фаз моба с лимитами его ранга.

    mode: strict → нарушения это ошибки (запрет сохранения); warning_only /
    manual_override → предупреждения. Возвращает {ok, errors, warnings, rank}.
    """
    mode = str(mode or "warning_only").strip()
    if mode not in VALIDATION_MODES:
        mode = "warning_only"
    data = data if isinstance(data, dict) else {}
    rank = str(data.get("mob_rank") or data.get("rank") or "").strip()
    limits = RANK_LIMITS.get(rank)
    errors: list[str] = []
    warnings: list[str] = []
    if not limits:
        warnings.append(f"Неизвестный ранг моба: «{rank or '—'}» — лимиты не проверены.")
        return {"ok": True, "errors": errors, "warnings": warnings, "rank": rank}

    rank_label = RANK_LABELS.get(rank, rank)
    issues: list[str] = []
    for field, key, label in _METRICS:
        count = _count(data.get(field))
        lo, hi = limits[key]
        if count > hi:
            issues.append(f"Слишком много {label}: {count} (лимит ранга «{rank_label}» — {hi}).")
        # Минимум осмысленен только для навыков; черты/фазы опциональны (0 — норма).
        elif key in _MIN_ENFORCED and count < lo:
            issues.append(f"Мало {label}: {count} (для ранга «{rank_label}» рекомендуется ≥ {lo}).")

    # Активных навыков за ход.
    per_turn = _safe_int(data.get("active_skills_per_turn_max"), 0)
    lo, hi = limits["per_turn"]
    if per_turn and per_turn > hi:
        issues.append(f"Активных навыков за ход {per_turn} превышает лимит ранга ({hi}).")

    if mode == "strict":
        errors.extend(issues)
    else:
        warnings.extend(issues)
    return {"ok": not errors, "errors": errors, "warnings": warnings, "rank": rank}
