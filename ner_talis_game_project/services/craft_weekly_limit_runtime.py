"""Per-player weekly limits for published crafting recipes (§29)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def week_key(now: datetime | None = None) -> str:
    year, week, _ = (now or datetime.now(timezone.utc)).isocalendar()
    return f"{year}-W{week:02d}"


def _rows(recipe: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in recipe.get("weekly_limits") or [] if isinstance(row, dict) and row.get("active", True)]


def usage(player: dict[str, Any], limit_id: str, *, week: str | None = None) -> int:
    state = player.get("craft_weekly_usage") or {}
    return int(((state.get(week or week_key()) or {}).get(str(limit_id)) or 0))


def remaining(player: dict[str, Any], row: dict[str, Any], *, week: str | None = None) -> int:
    maximum = max(0, int(float(row.get("max_per_week") or 0)))
    return max(0, maximum - usage(player, str(row.get("id") or ""), week=week))


def required_amount(row: dict[str, Any], *, quantity: int, result_amount: int = 1) -> int:
    kind = str(row.get("limit_type") or "recipe_count")
    if kind in {"result_count", "rare_result_count"}:
        return max(1, quantity) * max(1, result_amount)
    return max(1, quantity) if kind in {"recipe_count", "upgrade", "enchant", "purify", "disassemble"} else 1


def check(player: dict[str, Any], recipe: dict[str, Any], *, quantity: int, result_amount: int = 1) -> tuple[bool, str]:
    for row in _rows(recipe):
        needed = required_amount(row, quantity=quantity, result_amount=result_amount)
        if remaining(player, row) < needed:
            return False, str(row.get("exhausted_text") or "Недельный лимит ремесла исчерпан.")
    return True, ""


def consume(player: dict[str, Any], recipe: dict[str, Any], *, quantity: int, result_amount: int = 1) -> None:
    ok, message = check(player, recipe, quantity=quantity, result_amount=result_amount)
    if not ok:
        raise ValueError(message)
    week = week_key()
    bucket = player.setdefault("craft_weekly_usage", {}).setdefault(week, {})
    for row in _rows(recipe):
        limit_id = str(row.get("id") or "")
        if limit_id:
            bucket[limit_id] = int(bucket.get(limit_id) or 0) + required_amount(row, quantity=quantity, result_amount=result_amount)


def refund(player: dict[str, Any], recipe: dict[str, Any], *, quantity: int, result_amount: int = 1) -> None:
    bucket = player.setdefault("craft_weekly_usage", {}).setdefault(week_key(), {})
    for row in _rows(recipe):
        limit_id = str(row.get("id") or "")
        if limit_id:
            bucket[limit_id] = max(0, int(bucket.get(limit_id) or 0) - required_amount(row, quantity=quantity, result_amount=result_amount))


def admin_view(player: dict[str, Any], recipe: dict[str, Any]) -> list[dict[str, Any]]:
    return [{**row, "used": usage(player, str(row.get("id") or "")), "remaining": remaining(player, row), "week": week_key()} for row in _rows(recipe)]
