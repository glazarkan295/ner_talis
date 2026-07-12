"""Рантайм-чтение текстов бота из конструктора (full-import ТЗ §5.18 + §6/§14).

Единая точка, через которую игра берёт редактируемый текст по ключу. Включается
feature flag use_v2_texts (по умолчанию ВЫКЛ): пока флаг выключен или текст не
найден/не опубликован — возвращается переданный default (старый код-источник).
Так переход на V2-тексты происходит постепенно и безопасно.
"""

from __future__ import annotations

from typing import Any


def live_enabled() -> bool:
    from services import feature_flags_service as ff

    return ff.is_enabled("use_v2_texts")


def _pick_published(text_key: str, platform: str) -> dict[str, Any] | None:
    """Опубликованная запись по ключу. Точное совпадение платформы приоритетнее both."""
    from services import text_constructor_service as tcs

    best: dict[str, Any] | None = None
    for env in tcs.store().list(status=tcs.STATUS_PUBLISHED):  # noqa: F405
        data = env.get("data") or {}
        if str(data.get("text_key") or "") != text_key:
            continue
        rec_platform = str(data.get("platform") or "both")
        if rec_platform == platform:
            return data  # точное совпадение платформы — лучший выбор
        if rec_platform == "both" or platform == "both":
            best = data
    return best


def get_text(text_key: str, *, platform: str = "both",
             variables: dict[str, Any] | None = None, default: str = "") -> str:
    """Текст по ключу из конструктора или default.

    default возвращается, если флаг use_v2_texts выключен, либо текст не найден /
    не опубликован — игра продолжает работать на старом источнике."""
    if not live_enabled():
        return default
    data = _pick_published(str(text_key), str(platform or "both"))
    if data is None:
        return default
    from services import text_constructor_service as tcs

    rendered = tcs.render(data, variables)
    return rendered if rendered else default


def game_text(text_key: str, default: str, **variables: Any) -> str:
    """Короткий helper для синхронных игровых ответов без объекта доставки."""
    return get_text(text_key, variables=variables or None, default=default)
