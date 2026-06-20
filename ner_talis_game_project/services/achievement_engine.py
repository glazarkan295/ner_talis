"""Achievement engine — runtime: прогресс, выдача, ручная выдача/откат.

Работает поверх опубликованных достижений из achievement_service и состояния
игрока ``player["achievements"]``. Игровой код вызывает ``record_progress`` при
действиях игрока (kill_mob, reach_level, ...); движок обновляет прогресс и
выдаёт достижение при выполнении условий. Ручная выдача/откат — для админа.

Состояние игрока:
    player["achievements"] = {
        "earned":   { ach_id: {at, source, by, reason} },
        "progress": { ach_id: {"counts": {cond_index: number}} },
        "history":  [ {ach_id, at, source, by, reason, reward_status} ]  # capped
    }
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services import achievement_service as ach

_HISTORY_CAP = 500


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _state(player: dict[str, Any]) -> dict[str, Any]:
    state = player.get("achievements")
    if not isinstance(state, dict):
        state = {"earned": {}, "progress": {}, "history": []}
        player["achievements"] = state
    state.setdefault("earned", {})
    state.setdefault("progress", {})
    state.setdefault("history", [])
    return state


def is_earned(player: dict[str, Any], ach_id: str) -> bool:
    return str(ach_id) in _state(player).get("earned", {})


def _published() -> list[dict[str, Any]]:
    return ach.store().list(status=ach.STATUS_PUBLISHED)


def _conditions(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("conditions")
    return [c for c in raw if isinstance(c, dict)] if isinstance(raw, list) else []


def _evaluate(data: dict[str, Any], counts: dict[str, Any]) -> bool:
    """Выполнено ли достижение по текущему прогрессу и логике условий."""
    conditions = _conditions(data)
    if not conditions:
        return False
    met = []
    for idx, cond in enumerate(conditions):
        threshold = _num(cond.get("amount"), 1) or 1
        met.append(_num(counts.get(str(idx)), 0) >= threshold)
    logic = str(data.get("condition_logic") or "all")
    if logic == "any":
        return any(met)
    if logic == "n_of":
        need = int(_num(data.get("condition_n"), len(met)))
        return sum(1 for m in met if m) >= max(1, need)
    # all / ordered (порядок на этапе выдачи не форсируем) — нужны все.
    return all(met)


# --- Применение наград ------------------------------------------------------
_REWARD_KIND = {
    "experience": "experience", "exp_grains": "experience",
    "coins": "money", "stat_points": "stat_points", "skill_points": "skill_points",
    "item": "item", "unique_item": "item",
}
_COSMETIC = {"title", "emblem", "profile_icon", "passive_bonus"}


def apply_rewards(player: dict[str, Any], rewards: Any) -> tuple[list[str], list[str]]:
    """Выдать награды достижения игроку. Возвращает (строки, ошибки)."""
    if not isinstance(rewards, list):
        return [], []
    lines: list[str] = []
    errors: list[str] = []
    mapped: list[dict[str, Any]] = []
    for rw in rewards:
        if not isinstance(rw, dict):
            continue
        rtype = str(rw.get("type") or "").strip()
        amount = int(_num(rw.get("amount"), 1)) or 1
        if rtype in _REWARD_KIND:
            kind = _REWARD_KIND[rtype]
            item_id = "money_copper" if kind == "money" else (str(rw.get("item_id") or "") or rtype)
            mapped.append({"item_id": item_id, "amount": amount, "kind": kind})
        elif rtype == "title":
            titles = player.setdefault("titles", [])
            tid = str(rw.get("title_id") or rw.get("item_id") or "").strip()
            if tid and not any((isinstance(t, dict) and t.get("id") == tid) or t == tid for t in titles):
                titles.append({"id": tid, "name": rw.get("title_name") or tid})
            lines.append(f"Титул: {rw.get('title_name') or tid}")
        elif rtype in _COSMETIC:
            bucket = player.setdefault("achievement_rewards", {}).setdefault(rtype, [])
            bucket.append(rw)
            lines.append(rtype)
        else:
            # unlock_*/guild_points/event_currency/temp_buff — нужен отдельный
            # runtime; фиксируем как отложенную награду.
            player.setdefault("achievement_rewards", {}).setdefault("pending", []).append(rw)
    if mapped:
        try:
            from services.admin_panel_service import _apply_rewards_to_player
            lines.extend(_apply_rewards_to_player(player, mapped, source="achievement"))
        except Exception as exc:  # нет места в инвентаре и т.п.
            errors.append(str(exc))
    return lines, errors


def _notify(storage: Any, player: dict[str, Any], data: dict[str, Any], lines: list[str]) -> None:
    game_id = player.get("game_id") or player.get("id")
    if not game_id:
        return
    hidden = str(data.get("visibility") or "") in ("hidden_until_earned", "fully_hidden")
    name = data.get("name") or "Достижение"
    desc = data.get("short_description") or data.get("description") or ""
    header = "🏆 Скрытое достижение открыто!" if hidden else "🏆 Достижение получено!"
    text = f"{header}\n\n{name}"
    if desc:
        text += f"\n{desc}"
    if lines:
        text += "\n\nНаграда:\n" + "\n".join(f"• {line}" for line in lines)
    message = {"type": "achievement", "text": text, "created_at": _now_iso(), "source": "achievement"}
    enqueue = getattr(storage, "enqueue_bot_messages", None)
    if callable(enqueue):
        enqueue(game_id, [message])
    else:
        player.setdefault("pending_bot_messages", []).append(message)


def _append_history(state: dict[str, Any], entry: dict[str, Any]) -> None:
    history = state.setdefault("history", [])
    history.append(entry)
    if len(history) > _HISTORY_CAP:
        del history[:-_HISTORY_CAP]


def grant(
    storage: Any,
    player: dict[str, Any],
    ach_id: str,
    *,
    source: str = "auto",
    by: str = "",
    reason: str = "",
    save: bool = True,
    notify: bool = True,
) -> bool:
    """Выдать достижение игроку (идемпотентно, если не повторяемое)."""
    ach_id = str(ach_id)
    envelope = ach.store().get(ach_id)
    if envelope is None:
        raise ValueError(f"Достижение {ach_id} не найдено.")
    data = envelope.get("data") or {}
    state = _state(player)
    repeatable = bool(data.get("repeatable"))
    if ach_id in state["earned"] and not repeatable:
        return False
    lines, errors = apply_rewards(player, data.get("rewards"))
    reward_status = "error" if errors else "ok"
    state["earned"][ach_id] = {
        "at": _now_iso(), "source": source, "by": str(by or ""), "reason": str(reason or ""),
    }
    _append_history(state, {
        "ach_id": ach_id, "at": _now_iso(), "source": source,
        "by": str(by or ""), "reason": str(reason or ""),
        "reward_status": reward_status, "reward_errors": errors,
    })
    if notify:
        _notify(storage, player, data, lines)
    if save:
        storage.update_player(player)
    return True


def revoke(storage: Any, player: dict[str, Any], ach_id: str, *, by: str = "", reason: str = "", save: bool = True) -> bool:
    """Откатить выданное достижение (награды не возвращаются)."""
    ach_id = str(ach_id)
    state = _state(player)
    if ach_id not in state["earned"]:
        return False
    state["earned"].pop(ach_id, None)
    state["progress"].pop(ach_id, None)
    _append_history(state, {
        "ach_id": ach_id, "at": _now_iso(), "source": "manual_revoke",
        "by": str(by or ""), "reason": str(reason or ""), "reward_status": "revoked",
    })
    if save:
        storage.update_player(player)
    return True


def record_progress(
    storage: Any,
    player: dict[str, Any],
    event_type: str,
    amount: float = 1,
    target: str | None = None,
    *,
    save: bool = True,
) -> list[str]:
    """Хук игрового действия. Обновляет прогресс и выдаёт готовые достижения.

    Возвращает список id только что выданных достижений.
    """
    state = _state(player)
    newly: list[str] = []
    changed = False
    for envelope in _published():
        ach_id = str(envelope.get("id"))
        data = envelope.get("data") or {}
        if ach_id in state["earned"] and not bool(data.get("repeatable")):
            continue
        conditions = _conditions(data)
        matched = False
        counts = state["progress"].setdefault(ach_id, {}).setdefault("counts", {})
        for idx, cond in enumerate(conditions):
            if str(cond.get("type") or "") != str(event_type):
                continue
            ctarget = str(cond.get("target") or "").strip()
            if ctarget and ctarget != str(target or ""):
                continue
            counts[str(idx)] = _num(counts.get(str(idx)), 0) + _num(amount, 1)
            matched = True
        if matched:
            changed = True
            if _evaluate(data, counts):
                grant(storage, player, ach_id, source="auto", save=False)
                newly.append(ach_id)
    if changed and save:
        storage.update_player(player)
    return newly


# --- Представления ----------------------------------------------------------
def _progress_summary(data: dict[str, Any], counts: dict[str, Any]) -> str:
    conditions = _conditions(data)
    if not conditions:
        return ""
    done = sum(1 for idx, c in enumerate(conditions) if _num(counts.get(str(idx)), 0) >= (_num(c.get("amount"), 1) or 1))
    if len(conditions) == 1:
        threshold = int(_num(conditions[0].get("amount"), 1) or 1)
        current = int(_num(counts.get("0"), 0))
        return f"{min(current, threshold)} / {threshold}"
    return f"{done} / {len(conditions)} условий"


def player_view(player: dict[str, Any]) -> dict[str, Any]:
    """Для профиля игрока (ТЗ §21): без формул/ID, скрытые как ???."""
    state = _state(player)
    earned_ids = set(state.get("earned", {}))
    earned: list[dict[str, Any]] = []
    in_progress: list[dict[str, Any]] = []
    for envelope in _published():
        ach_id = str(envelope.get("id"))
        data = envelope.get("data") or {}
        visibility = str(data.get("visibility") or "open")
        if visibility == "admin":
            continue
        if ach_id in earned_ids:
            earned.append({
                "name": data.get("name"), "description": data.get("short_description") or data.get("description"),
                "rarity": data.get("rarity"), "category": data.get("category"),
                "at": state["earned"][ach_id].get("at"),
            })
            continue
        if visibility == "fully_hidden":
            continue
        counts = state.get("progress", {}).get(ach_id, {}).get("counts", {})
        if visibility == "hidden_until_earned":
            in_progress.append({"name": "???", "hidden": True, "progress": _progress_summary(data, counts) if counts else ""})
        else:
            in_progress.append({
                "name": data.get("name"), "description": data.get("short_description"),
                "rarity": data.get("rarity"), "category": data.get("category"),
                "progress": _progress_summary(data, counts),
            })
    return {"earned": earned, "inProgress": in_progress, "earnedCount": len(earned)}


def admin_player_progress(player: dict[str, Any]) -> dict[str, Any]:
    """Полная картина для админа (включая скрытые/служебные, прогресс, историю)."""
    state = _state(player)
    earned_ids = set(state.get("earned", {}))
    rows: list[dict[str, Any]] = []
    for envelope in _published():
        ach_id = str(envelope.get("id"))
        data = envelope.get("data") or {}
        counts = state.get("progress", {}).get(ach_id, {}).get("counts", {})
        rows.append({
            "id": ach_id, "name": data.get("name"), "rarity": data.get("rarity"),
            "visibility": data.get("visibility"), "category": data.get("category"),
            "earned": ach_id in earned_ids,
            "earnedAt": state["earned"].get(ach_id, {}).get("at"),
            "source": state["earned"].get(ach_id, {}).get("source"),
            "progress": _progress_summary(data, counts),
        })
    rows.sort(key=lambda r: (not r["earned"], str(r.get("name") or "")))
    return {"achievements": rows, "history": list(reversed(state.get("history", [])))[:100]}
