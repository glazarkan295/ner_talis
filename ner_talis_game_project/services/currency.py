"""Единое форматирование игровой валюты по номиналам.

Базовая единица — медная монета. Курс:
1 серебряная = 1 000, 1 золотая = 1 000 000, 1 магическая золотая = 1 000 000 000,
1 древняя = 500 000 000 000 медных.
"""

from __future__ import annotations

# (стоимость в меди, краткая метка, полная форма род. падежа мн. числа)
DENOMINATIONS = [
    (500_000_000_000, "древн.", "древних"),
    (1_000_000_000, "маг. зол.", "магических золотых"),
    (1_000_000, "зол.", "золотых"),
    (1_000, "сер.", "серебряных"),
    (1, "мед.", "медных"),
]


def _split(copper: int) -> list[tuple[int, str, str]]:
    copper = max(0, int(copper or 0))
    result: list[tuple[int, str, str]] = []
    for cost, short, full in DENOMINATIONS[:-1]:
        amount, copper = divmod(copper, cost)
        if amount:
            result.append((amount, short, full))
    if copper or not result:
        result.append((copper, "мед.", "медных"))
    return result


def format_money(copper: int) -> str:
    """Краткий вид: «10 сер. 500 мед.» — для профиля и баланса."""
    return " ".join(f"{amount} {short}" for amount, short, _full in _split(copper))


def format_price(copper: int) -> str:
    """Краткий вид по номиналам с подписью: «13 маг. зол. 6 зол. 400 мед. монет».

    Используется в торговле и карточках. Сокращения номиналов: древн., маг. зол.,
    зол., сер., мед.
    """
    return " ".join(f"{amount} {short}" for amount, short, _full in _split(copper)) + " монет"
