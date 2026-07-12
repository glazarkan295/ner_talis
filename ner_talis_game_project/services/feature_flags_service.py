"""Feature flags для постепенного перехода игры на V2-данные (ТЗ §14, AC#12).

После импорта контента в конструкторы игра должна уметь читать данные из
V2-хранилища ВКЛючаемо по доменам, оставляя старый код как fallback (§6/§14).
Этот сервис хранит набор флагов ``use_v2_*`` и даёт рантайму единую точку
проверки ``is_enabled(domain)``.

Безопасность: все флаги по умолчанию ВЫКЛючены — поведение игры не меняется,
пока админ явно не включит источник. Хранение — отдельный JSON
(env FEATURE_FLAGS_PATH, по умолчанию data/feature_flags.json).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

# (имя флага, человекочитаемая подпись) — список доменов из ТЗ §14.
FLAG_SPECS: tuple[tuple[str, str], ...] = (
    ("use_v2_items", "Предметы"),
    ("use_v2_effects", "Эффекты"),
    ("use_v2_skills", "Навыки"),
    ("use_v2_mobs", "Мобы"),
    ("use_v2_locations", "Локации"),
    ("use_v2_events", "События"),
    ("use_v2_buttons", "Кнопки"),
    ("use_v2_transitions", "Переходы"),
    ("use_v2_camps", "Лагеря"),
    ("use_v2_quests", "Задания"),
    ("use_v2_npc", "NPC"),
    ("use_v2_crafting", "Ремесло"),
    ("use_v2_shops", "Рынки"),
    ("use_v2_achievements", "Достижения"),
    ("use_v2_fines", "Штрафы"),
    ("use_v2_texts", "Тексты"),
    ("use_v2_reputation", "Репутация"),
)

FLAGS: tuple[str, ...] = tuple(name for name, _ in FLAG_SPECS)
FLAG_LABELS: dict[str, str] = {name: label for name, label in FLAG_SPECS}

# Флаги, которые РЕАЛЬНО читаются runtime'ом (15-CODEX §5.4): остальные пока
# только в админке и не меняют gameplay — UI обязан это показывать, чтобы не
# вводить администратора в заблуждение.
RUNTIME_WIRED: frozenset[str] = frozenset({
    "use_v2_locations",  # location_runtime.live_enabled (поиск/бой/лимиты)
    "use_v2_buttons",    # city_runtime.live_enabled (навигация города)
    "use_v2_texts",      # message_delivery → text_runtime (фоновые уведомления)
})

_LOCK = threading.Lock()


def _path() -> Path:
    override = os.environ.get("FEATURE_FLAGS_PATH")
    if override:
        return Path(override)
    from project_paths import project_path

    return project_path("data", "feature_flags.json")


def _read_raw() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_raw(data: dict[str, Any]) -> None:
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def all_flags() -> dict[str, bool]:
    """Все известные флаги → bool (неизвестные/отсутствующие = False)."""
    raw = _read_raw()
    return {name: bool(raw.get(name, False)) for name in FLAGS}


def is_enabled(name: str) -> bool:
    """Единая точка проверки для рантайма. Неизвестный флаг → False (fallback)."""
    if name not in FLAG_LABELS:
        return False
    return bool(_read_raw().get(name, False))


def set_flag(name: str, value: bool) -> dict[str, bool]:
    """Установить флаг. Возвращает полный набор флагов после изменения."""
    if name not in FLAG_LABELS:
        raise ValueError(f"Неизвестный feature flag: {name}")
    with _LOCK:
        raw = _read_raw()
        raw[name] = bool(value)
        # Чистим мусорные ключи, оставляем только известные флаги.
        cleaned = {k: bool(raw.get(k, False)) for k in FLAGS}
        _write_raw(cleaned)
    return cleaned


def meta() -> dict[str, Any]:
    return {"flags": [
        {"name": n, "label": FLAG_LABELS[n], "wired": n in RUNTIME_WIRED}
        for n in FLAGS
    ]}
