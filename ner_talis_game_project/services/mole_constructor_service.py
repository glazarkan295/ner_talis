"""Конструктор криминального сервиса «Информатор Крот» (ТЗ 21 §3).

Запись = конфигурация Крота: продажа информации о местоположении игроков,
магический компас и заказ NPC-убийц. ВАЖНО (§3.1): заказ берёт бот/NPC-система,
а не реальные игроки — это слой данных/правил для авторинга.

Обязательные запреты заказа (§3.5):
* нельзя заказать игрока при разнице уровней больше 400;
* нельзя заказать игрока, который слабее заказчика более чем в 2 раза по уровню.

Хранение — EntityStore (data/mole_constructor.json). Слой данных + валидация +
предпросмотр + чистая проверка допустимости заказа (тестируемая).
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")

# Режимы поиска информации о местоположении (§3.2).
INFO_SEARCH_MODES = (
    "by_nick", "by_id", "by_level", "by_level_range", "region", "exact",
)
INFO_SEARCH_LABELS = {
    "by_nick": "Поиск по нику", "by_id": "Поиск по ID",
    "by_level": "Игроки определённого уровня", "by_level_range": "Диапазон уровней",
    "region": "Приблизительный регион", "exact": "Точная локация",
}
# Магический компас (§3.3): переносит сразу или ведёт маршрутом.
COMPASS_MODES = ("teleport", "route")
COMPASS_MODE_LABELS = {"teleport": "Переносит сразу", "route": "Ведёт маршрутом"}
# Категории убийц (§3.6).
ASSASSIN_CATEGORIES = (
    "cheap", "normal", "experienced", "elite", "magic", "poisoner", "tracker",
    "group", "rare_event", "mole_special",
)
ASSASSIN_CATEGORY_LABELS = {
    "cheap": "Дешёвый убийца", "normal": "Обычный убийца",
    "experienced": "Опытный убийца", "elite": "Элитный убийца",
    "magic": "Магический убийца", "poisoner": "Отравитель",
    "tracker": "Следопыт", "group": "Группа убийц",
    "rare_event": "Редкая категория события", "mole_special": "Особая категория Крота",
}
# Политика возврата средств (§3.4/§3.7).
REFUND_POLICIES = ("full", "partial", "none")
REFUND_POLICY_LABELS = {"full": "Полный возврат", "partial": "Частичный возврат", "none": "Без возврата"}
CURRENCIES = ("copper", "silver", "gold", "magic_gold", "ancient_coin")

# Обязательные пороги запретов заказа (§3.5) — значения по умолчанию.
DEFAULT_MAX_LEVEL_DIFF = 400
DEFAULT_WEAKER_RATIO = 2.0

_store = EntityStore(
    env_var="MOLE_CONSTRUCTOR_PATH",
    default_rel="data/mole_constructor.json",
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


def check_order_allowed(
    orderer_level: Any,
    target_level: Any,
    *,
    max_level_diff: Any = DEFAULT_MAX_LEVEL_DIFF,
    weaker_ratio: Any = DEFAULT_WEAKER_RATIO,
) -> dict[str, Any]:
    """Чистая проверка обязательных запретов заказа (§3.5).

    Возвращает {"allowed": bool, "reason": str}. Запрещает заказ, если разница
    уровней больше ``max_level_diff`` (по умолчанию 400) или если цель слабее
    заказчика более чем в ``weaker_ratio`` раз по уровню (по умолчанию ×2).
    """
    o = _num(orderer_level)
    t = _num(target_level)
    if o is None or t is None:
        return {"allowed": False, "reason": "Не указан уровень заказчика или цели."}
    cap = _num(max_level_diff)
    if cap is None:
        cap = DEFAULT_MAX_LEVEL_DIFF
    if abs(o - t) > cap:
        return {"allowed": False, "reason": f"Нельзя заказать игрока: разница уровней больше {int(cap)}."}
    ratio = _num(weaker_ratio) or DEFAULT_WEAKER_RATIO
    if ratio > 0 and t > 0 and o > ratio * t:
        return {"allowed": False, "reason": f"Нельзя заказать игрока, который слабее заказчика более чем в {ratio:g} раза по уровню."}
    return {"allowed": True, "reason": ""}


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not str(data.get("name") or "").strip():
        errors.append("Не заполнено название сервиса Крота.")
    if not str(data.get("location_id") or "").strip() and not str(data.get("city_id") or "").strip():
        warnings.append("Сервис не привязан к локации или городу.")

    # Информация о местоположении (§3.2).
    for mode in (data.get("info_search_modes") or []):
        m = str(mode or "").strip()
        if m and m not in INFO_SEARCH_MODES:
            warnings.append(f"Режим поиска «{m}» не из списка.")
    for key, label in (("info_cost", "Стоимость информации"),
                       ("info_cooldown_seconds", "Кулдаун информации"),
                       ("info_delay_seconds", "Задержка получения информации"),
                       ("info_freshness_seconds", "Время актуальности информации")):
        if data.get(key) not in (None, "") and (_num(data.get(key)) is None or _num(data.get(key)) < 0):
            errors.append(f"{label}: неотрицательное число.")
    for key, label in (("info_error_chance", "Шанс ошибки"),
                       ("info_stale_chance", "Шанс устаревшей информации")):
        if data.get(key) not in (None, ""):
            num = _num(data.get(key))
            if num is None or not (0 <= num <= 100):
                errors.append(f"{label}: должно быть 0–100.")

    # Магический компас (§3.3).
    if data.get("compass_enabled"):
        cmode = str(data.get("compass_mode") or "").strip()
        if cmode and cmode not in COMPASS_MODES:
            warnings.append(f"Режим компаса «{cmode}» не из списка.")
        if (_num(data.get("compass_cost")) or 0) <= 0:
            warnings.append("Магический компас включён, но стоимость не задана (услуга задумана дорогой).")
        if data.get("compass_cost") not in (None, "") and (_num(data.get("compass_cost")) is None or _num(data.get("compass_cost")) < 0):
            errors.append("Стоимость компаса: неотрицательное число.")

    # Заказ убийц (§3.4) — числовые ограничения.
    for key, label in (("order_attempts", "Количество попыток"),
                       ("order_attack_cooldown_seconds", "Кулдаун между нападениями"),
                       ("order_duration_seconds", "Срок действия заказа")):
        if data.get(key) not in (None, "") and (_num(data.get(key)) is None or _num(data.get(key)) < 0):
            errors.append(f"{label}: неотрицательное число.")
    refund = str(data.get("order_refund_policy") or "").strip()
    if refund and refund not in REFUND_POLICIES:
        warnings.append(f"Политика возврата «{refund}» не из списка.")

    # Обязательные пороги запретов (§3.5).
    if data.get("ban_max_level_diff") not in (None, ""):
        num = _num(data.get("ban_max_level_diff"))
        if num is None or num < 0:
            errors.append("Порог разницы уровней: неотрицательное число.")
    if data.get("ban_weaker_ratio") not in (None, ""):
        num = _num(data.get("ban_weaker_ratio"))
        if num is None or num < 1:
            errors.append("Множитель «слабее в N раз»: число не меньше 1.")

    # Категории убийц (§3.6) — баланс по оплате (§3.7).
    for i, cat in enumerate(data.get("assassin_categories") or [], start=1):
        if not isinstance(cat, dict):
            continue
        ckey = str(cat.get("category") or "").strip()
        if ckey and ckey not in ASSASSIN_CATEGORIES:
            warnings.append(f"Категория #{i}: «{ckey}» не из списка.")
        for fkey, flabel in (("price", "цена"), ("level", "уровень"),
                             ("count", "количество"), ("attempts", "попыток")):
            if cat.get(fkey) not in (None, "") and (_num(cat.get(fkey)) is None or _num(cat.get(fkey)) < 0):
                errors.append(f"Категория #{i}: {flabel} — неотрицательное число.")
        if cat.get("success_chance") not in (None, ""):
            num = _num(cat.get("success_chance"))
            if num is None or not (0 <= num <= 100):
                errors.append(f"Категория #{i}: шанс успеха должен быть 0–100.")

    # Баланс цены (§3.7): min ≤ max, множители неотрицательные.
    pmin = _num(data.get("price_min"))
    pmax = _num(data.get("price_max"))
    if pmin is not None and pmax is not None and pmin > pmax:
        errors.append("Минимальная цена не может быть больше максимальной.")
    for key, label in (("price_base", "Базовая цена"),
                       ("mult_target_level", "Множитель по уровню цели"),
                       ("mult_orderer_level", "Множитель по уровню заказчика"),
                       ("mult_distance", "Множитель по расстоянию"),
                       ("mult_category", "Множитель по категории"),
                       ("mult_urgency", "Множитель за срочность"),
                       ("mult_group", "Множитель за группу"),
                       ("mult_stealth", "Множитель за скрытность"),
                       ("mole_commission", "Комиссия Крота")):
        if data.get(key) not in (None, "") and (_num(data.get(key)) is None or _num(data.get(key)) < 0):
            errors.append(f"{label}: неотрицательное число.")

    # Тексты без HTML.
    for key in ("name", "description"):
        if _has_html(data.get(key)):
            errors.append(f"В поле «{key}» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def preview(data: dict[str, Any]) -> dict[str, Any]:
    """Предпросмотр услуг Крота для игрока."""
    data = data or {}
    modes = [INFO_SEARCH_LABELS.get(str(m), str(m)) for m in (data.get("info_search_modes") or [])]
    cats = []
    for cat in (data.get("assassin_categories") or []):
        if isinstance(cat, dict):
            cats.append({
                "category": ASSASSIN_CATEGORY_LABELS.get(str(cat.get("category") or ""), str(cat.get("category") or "—")),
                "price": cat.get("price"),
                "success_chance": cat.get("success_chance"),
            })
    return {
        "name": data.get("name") or "Информатор Крот",
        "info_modes": modes,
        "info_cost": data.get("info_cost"),
        "compass_enabled": bool(data.get("compass_enabled")),
        "compass_cost": data.get("compass_cost"),
        "assassin_categories": cats,
        "ban_max_level_diff": data.get("ban_max_level_diff") if data.get("ban_max_level_diff") not in (None, "") else DEFAULT_MAX_LEVEL_DIFF,
        "ban_weaker_ratio": data.get("ban_weaker_ratio") if data.get("ban_weaker_ratio") not in (None, "") else DEFAULT_WEAKER_RATIO,
    }
