"""Прочность инструментов добычи (удочка, топор дровосека, шахтёрская кирка).

Каждый инструмент даёт 10 использований; инструменты стакаются. Полный запас
использований стака = (кол-во − 1) × 10 + остаток текущего инструмента. При трате
10 использований расходуется ровно один инструмент:
    1 удочка → 10 использований, 3 удочки → 30, 14 удочек → 140.

Счётчик остатка текущего инструмента хранится в поле ``tool_uses_left`` на самом
стаке предмета и переживает докупку (новые инструменты просто увеличивают
количество). Места применения топора/кирки подключат spend_tool_use позже.
"""

from __future__ import annotations

from typing import Any, Iterable

TOOL_USES_PER_UNIT = 10
USES_FIELD = "tool_uses_left"


def _names(names: Iterable[str] | None) -> set[str]:
    return {str(name).strip().casefold() for name in (names or []) if str(name).strip()}


def _matches(item: dict[str, Any], item_id: str, names: set[str]) -> bool:
    identity = str(item.get("id") or item.get("item_id") or "").strip()
    name = str(item.get("name") or item.get("name_ru") or "").strip().casefold()
    return identity == item_id or (bool(names) and name in names)


def find_tool_stack(player: dict[str, Any], item_id: str, names: Iterable[str] | None = None) -> dict[str, Any] | None:
    name_set = _names(names)
    inventory = player.get("inventory")
    for item in inventory if isinstance(inventory, list) else []:
        if not isinstance(item, dict):
            continue
        if int(item.get("amount", 1) or 1) <= 0:
            continue
        if _matches(item, item_id, name_set):
            return item
    return None


def player_has_tool(player: dict[str, Any], item_id: str, names: Iterable[str] | None = None) -> bool:
    return find_tool_stack(player, item_id, names) is not None


def tool_uses_left(player: dict[str, Any], item_id: str, names: Iterable[str] | None = None) -> int:
    stack = find_tool_stack(player, item_id, names)
    if stack is None:
        return 0
    amount = max(0, int(stack.get("amount", 1) or 1))
    if amount <= 0:
        return 0
    left = int(stack.get(USES_FIELD, TOOL_USES_PER_UNIT) or TOOL_USES_PER_UNIT)
    left = max(1, min(TOOL_USES_PER_UNIT, left))
    return (amount - 1) * TOOL_USES_PER_UNIT + left


def spend_tool_use(player: dict[str, Any], item_id: str, names: Iterable[str] | None = None) -> bool:
    """Тратит одно использование инструмента. Возвращает False, если инструмента нет.

    При исчерпании текущего инструмента (10 использований) расходуется один
    инструмент из стака; когда расходуется последний — стак удаляется.
    """
    stack = find_tool_stack(player, item_id, names)
    if stack is None:
        return False
    amount = max(0, int(stack.get("amount", 1) or 1))
    if amount <= 0:
        return False
    left = max(1, min(TOOL_USES_PER_UNIT, int(stack.get(USES_FIELD, TOOL_USES_PER_UNIT) or TOOL_USES_PER_UNIT)))
    left -= 1
    if left <= 0:
        amount -= 1
        if amount <= 0:
            inventory = player.get("inventory")
            if isinstance(inventory, list):
                try:
                    inventory.remove(stack)
                except ValueError:
                    stack["amount"] = 0
            try:
                from services.inventory_service import recalculate_inventory_overflow

                recalculate_inventory_overflow(player)
            except Exception:
                pass
        else:
            stack["amount"] = amount
            stack[USES_FIELD] = TOOL_USES_PER_UNIT
    else:
        stack[USES_FIELD] = left
    return True
