"""Shared inventory helpers with stacking, capacity and overload penalties."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.derived_stats_service import safe_int
from services.item_registry import build_inventory_item, inventory_stack_limit_from_definition, slugify_fallback_item_id

OVERFLOW_EFFECT_ID = "inventory_overflow_penalty"


@dataclass
class InventoryAddResult:
    requested: int = 0
    added: int = 0
    added_to_regular: int = 0
    added_to_overflow: int = 0
    discarded: int = 0
    overflow_slots_used: int = 0
    overflow_slots_max: int = 0

    @property
    def full(self) -> bool:
        return self.discarded > 0


def max_regular_slots(player: dict[str, Any]) -> int:
    return max(
        0,
        safe_int(
            player.get("inventory_capacity")
            or player.get("max_inventory_slots")
            or player.get("inventory_slots"),
            20,
        ),
    )


def max_overflow_slots(player: dict[str, Any]) -> int:
    # 10 обычных слотов дают 1 дополнительный слот. При 0-9 обычных слотов доп. слотов нет.
    return max_regular_slots(player) // 10


def is_overflow_item(item: Any) -> bool:
    return isinstance(item, dict) and bool(item.get("overflow_slot") or item.get("storage_type") == "overflow")


def regular_slot_count(player: dict[str, Any]) -> int:
    return sum(1 for item in player.get("inventory", []) if isinstance(item, dict) and not is_overflow_item(item))


def overflow_slot_count(player: dict[str, Any]) -> int:
    return sum(1 for item in player.get("inventory", []) if is_overflow_item(item))


def _item_identifier(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("item_id") or slugify_fallback_item_id(str(item.get("name") or "item")))


def _is_stackable_item(item: dict[str, Any]) -> bool:
    """Return True when this inventory entry may share a stack.

    Older admin/system-issued entries could have a unique ``id`` but the same
    ``item_id`` as a registry stackable item.  Using ``id`` as the stack key for
    those entries created phantom extra slots instead of filling the existing
    stack.  Non-stackable equipment still keeps per-instance identity.
    """

    if not isinstance(item, dict):
        return False
    if item.get("stackable") is True:
        return True
    max_stack = safe_int(item.get("max_stack") or item.get("stack_size"), 1)
    return max_stack > 1


def _stack_identifier(item: dict[str, Any]) -> str:
    """Canonical key used only for merging stackable inventory entries."""

    if _is_stackable_item(item):
        item_id = item.get("item_id")
        if item_id:
            return str(item_id)
    return _item_identifier(item)


def _apply_stack_limit(item: dict[str, Any]) -> dict[str, Any]:
    limit = max(1, inventory_stack_limit_from_definition(item))
    item["max_stack"] = limit
    item["stackable"] = limit > 1
    return item


def _prepare_item(item: dict[str, Any], amount: int | None = None, *, default_source: str | None = None, default_category: str | None = None) -> dict[str, Any]:
    prepared = dict(item)
    if amount is not None:
        prepared["amount"] = amount
    prepared.setdefault("amount", 1)
    item_id = _item_identifier(prepared)
    prepared.setdefault("id", item_id)
    prepared.setdefault("item_id", item_id)
    if default_source:
        prepared.setdefault("source", default_source)
    if default_category:
        prepared.setdefault("category", default_category)
    return _apply_stack_limit(prepared)


def _apply_storage_markers(item: dict[str, Any], *, overflow: bool) -> None:
    if overflow:
        item["overflow_slot"] = True
        item["storage_type"] = "overflow"
        item["inventory_status"] = "Перегруз"
        stats = item.setdefault("stats", [])
        if isinstance(stats, list) and not any("доп. слоте" in str(line).casefold() for line in stats):
            stats.append("Хранится в доп. слоте инвентаря")
    else:
        item.pop("overflow_slot", None)
        item.pop("storage_type", None)
        item.pop("inventory_status", None)
        stats = item.get("stats")
        if isinstance(stats, list):
            item["stats"] = [line for line in stats if "доп. слоте" not in str(line).casefold()]


def rebalance_overflow_slots(player: dict[str, Any]) -> None:
    """Move overflow stacks back to regular slots when free regular space appears."""

    inventory = player.setdefault("inventory", [])
    if not isinstance(inventory, list):
        player["inventory"] = []
        return
    regular_limit = max_regular_slots(player)
    for item in inventory:
        if regular_slot_count(player) >= regular_limit:
            break
        if is_overflow_item(item):
            _apply_storage_markers(item, overflow=False)


def normalize_inventory_stacks(player: dict[str, Any]) -> None:
    """Merge old duplicate stack entries and drop empty phantom stacks.

    This is intentionally conservative: only entries that are explicitly
    stackable or have ``max_stack > 1`` are merged by ``item_id``.  Equipment and
    other one-off instances are left untouched.
    """

    inventory = player.setdefault("inventory", [])
    if not isinstance(inventory, list):
        player["inventory"] = []
        return

    normalized: list[Any] = []
    open_stacks: dict[str, list[dict[str, Any]]] = {}

    def merge_metadata(target: dict[str, Any], source: dict[str, Any]) -> None:
        for meta_key in (
            "icon",
            "asset_icon",
            "category",
            "type",
            "subtype",
            "quality",
            "max_stack",
            "stackable",
            "source",
            "sell_price_copper",
            "energy_restore",
            "use_effect",
        ):
            if target.get(meta_key) is None and source.get(meta_key) is not None:
                target[meta_key] = source.get(meta_key)

    for entry in inventory:
        if not isinstance(entry, dict):
            normalized.append(entry)
            continue
        amount = safe_int(entry.get("amount"), 1)
        if amount <= 0:
            continue
        entry = _apply_stack_limit(entry)
        if not _is_stackable_item(entry):
            for _index in range(amount):
                new_entry = dict(entry)
                new_entry["amount"] = 1
                normalized.append(new_entry)
            continue
        key = _stack_identifier(entry)
        if entry.get("item_id"):
            entry["id"] = str(entry.get("item_id"))
        max_stack_value = max(1, safe_int(entry.get("max_stack"), 1))
        stacks = open_stacks.setdefault(key, [])
        remaining = amount
        for existing in stacks:
            current = max(0, safe_int(existing.get("amount"), 0))
            free = max_stack_value - current
            if free <= 0:
                continue
            added = min(free, remaining)
            existing["amount"] = current + added
            merge_metadata(existing, entry)
            remaining -= added
            if remaining <= 0:
                break
        while remaining > 0:
            new_amount = min(max_stack_value, remaining)
            new_entry = dict(entry)
            new_entry["amount"] = new_amount
            new_entry["max_stack"] = max_stack_value
            new_entry["stackable"] = True
            normalized.append(new_entry)
            stacks.append(new_entry)
            remaining -= new_amount

    inventory[:] = normalized


def recalculate_inventory_overflow(player: dict[str, Any]) -> dict[str, int | bool]:
    """Refresh overload counters and the derived active penalty effect."""

    inventory = player.setdefault("inventory", [])
    if not isinstance(inventory, list):
        inventory = []
        player["inventory"] = inventory

    normalize_inventory_stacks(player)

    rebalance_overflow_slots(player)
    overflow_used = overflow_slot_count(player)
    overflow_max = max_overflow_slots(player)
    player["overflow_inventory_slots_used"] = overflow_used
    player["overflow_inventory_slots_max"] = overflow_max
    player["inventory_overflow_no_escape"] = overflow_used >= 4

    effects = player.setdefault("active_effects", [])
    if not isinstance(effects, list):
        effects = []
        player["active_effects"] = effects
    effects[:] = [effect for effect in effects if not (isinstance(effect, dict) and effect.get("id") == OVERFLOW_EFFECT_ID)]

    if overflow_used > 0:
        level = min(4, overflow_used)
        penalties_by_level = {
            1: {"bonus_dodge": -2, "bonus_accuracy": -1},
            2: {"bonus_dodge": -5, "bonus_accuracy": -3, "bonus_physical_defense": -2},
            3: {"bonus_dodge": -10, "bonus_accuracy": -6, "bonus_physical_defense": -5, "bonus_strength": -1, "bonus_endurance": -1},
            4: {"bonus_dodge": -15, "bonus_accuracy": -10, "bonus_physical_defense": -10, "bonus_strength": -2, "bonus_endurance": -2},
        }
        description = (
            f"Занято доп. слотов: {overflow_used}/{overflow_max}. "
            "Освободите инвентарь, чтобы снять штраф."
        )
        if overflow_used >= 4:
            description += " При 4+ занятых доп. слотах нельзя сбежать от противника."
        effects.append(
            {
                "id": OVERFLOW_EFFECT_ID,
                "name": "Перегруз инвентаря",
                "source": "inventory_overflow",
                "stat_modifiers": penalties_by_level[level],
                "description": description,
            }
        )
    return {
        "overflow_used": overflow_used,
        "overflow_max": overflow_max,
        "no_escape": player["inventory_overflow_no_escape"],
    }


def add_inventory_item(
    player: dict[str, Any],
    item: dict[str, Any] | str,
    amount: int = 1,
    *,
    item_id: str | None = None,
    max_stack: int | None = None,
    default_source: str | None = None,
    default_category: str | None = None,
) -> InventoryAddResult:
    """Add an item respecting stacks, normal slots and overflow slots.

    Existing stacks are filled first. New stacks use regular slots first, then
    overflow slots. If overflow slots are also full, only the fitting amount is
    added and the remainder is discarded.
    """

    amount = max(0, safe_int(amount, 0))
    result = InventoryAddResult(requested=amount)
    if amount <= 0:
        recalculate_inventory_overflow(player)
        return result

    if isinstance(item, str):
        prepared = build_inventory_item(item, amount, item_id=item_id, max_stack=max_stack)
    else:
        prepared = dict(item)
        if item_id:
            prepared["id"] = item_id
            prepared["item_id"] = item_id
        if max_stack:
            prepared["max_stack"] = max_stack
        prepared = _prepare_item(prepared, amount, default_source=default_source, default_category=default_category)

    if default_source:
        prepared.setdefault("source", default_source)
    if default_category:
        prepared.setdefault("category", default_category)

    canonical_id = _stack_identifier(prepared)
    if _is_stackable_item(prepared):
        prepared["item_id"] = canonical_id
        prepared["id"] = canonical_id
    else:
        prepared.setdefault("item_id", canonical_id)
        prepared.setdefault("id", canonical_id)
    prepared = _apply_stack_limit(prepared)
    if max_stack is not None:
        prepared["max_stack"] = max(1, safe_int(max_stack, 1))
        prepared["stackable"] = prepared["max_stack"] > 1
    max_stack_value = max(1, safe_int(prepared.get("max_stack"), 1))

    remaining = amount
    inventory = player.setdefault("inventory", [])
    if not isinstance(inventory, list):
        inventory = []
        player["inventory"] = inventory

    for existing in inventory:
        if not isinstance(existing, dict):
            continue
        if _stack_identifier(existing) != canonical_id:
            continue
        _apply_stack_limit(existing)
        current = max(0, safe_int(existing.get("amount"), 1))
        existing_limit = max(1, safe_int(existing.get("max_stack"), max_stack_value))
        free = min(max_stack_value, existing_limit) - current
        if free <= 0:
            continue
        added = min(free, remaining)
        existing["amount"] = current + added
        for key in ("icon", "asset_icon", "category", "type", "subtype", "quality", "max_stack", "stackable", "source"):
            if prepared.get(key) is not None:
                existing.setdefault(key, prepared.get(key))
        if is_overflow_item(existing):
            result.added_to_overflow += added
        else:
            result.added_to_regular += added
        remaining -= added
        if remaining <= 0:
            result.added = amount
            recalculate_inventory_overflow(player)
            counts = recalculate_inventory_overflow(player)
            result.overflow_slots_used = int(counts["overflow_used"])
            result.overflow_slots_max = int(counts["overflow_max"])
            return result

    while remaining > 0:
        added = min(max_stack_value, remaining)
        use_overflow = False
        if regular_slot_count(player) < max_regular_slots(player):
            use_overflow = False
        elif overflow_slot_count(player) < max_overflow_slots(player):
            use_overflow = True
        else:
            result.discarded += remaining
            break

        new_item = dict(prepared)
        new_item["amount"] = added
        if _is_stackable_item(new_item):
            new_item["id"] = canonical_id
            new_item["item_id"] = canonical_id
        else:
            new_item.setdefault("id", canonical_id)
            new_item.setdefault("item_id", canonical_id)
        _apply_storage_markers(new_item, overflow=use_overflow)
        inventory.append(new_item)
        if use_overflow:
            result.added_to_overflow += added
        else:
            result.added_to_regular += added
        remaining -= added

    result.added = result.added_to_regular + result.added_to_overflow
    counts = recalculate_inventory_overflow(player)
    result.overflow_slots_used = int(counts["overflow_used"])
    result.overflow_slots_max = int(counts["overflow_max"])
    return result


def inventory_add_overflow_notice(result: InventoryAddResult | None, item_name: str | None = None) -> str:
    """Return a short Russian note when new items were placed into overflow slots."""

    if result is None or safe_int(getattr(result, "added_to_overflow", 0), 0) <= 0:
        return ""
    amount = safe_int(getattr(result, "added_to_overflow", 0), 0)
    label = f"{item_name} ×{amount}" if item_name else f"×{amount}"
    return f" В доп. слот попало: {label}."


def inventory_add_discard_notice(result: InventoryAddResult | None, item_name: str | None = None) -> str:
    """Return a short note when part of a reward did not fit into any slot."""

    if result is None or safe_int(getattr(result, "discarded", 0), 0) <= 0:
        return ""
    amount = safe_int(getattr(result, "discarded", 0), 0)
    label = f"{item_name} ×{amount}" if item_name else f"×{amount}"
    return f" Не поместилось: {label}."


def inventory_add_result_notice(result: InventoryAddResult | None, item_name: str | None = None) -> str:
    """Return combined reward placement notes for player-facing messages."""

    return inventory_add_overflow_notice(result, item_name) + inventory_add_discard_notice(result, item_name)


def remove_empty_stacks_and_recalculate(player: dict[str, Any]) -> None:
    inventory = player.setdefault("inventory", [])
    if isinstance(inventory, list):
        inventory[:] = [item for item in inventory if not isinstance(item, dict) or safe_int(item.get("amount"), 1) > 0]
    recalculate_inventory_overflow(player)
