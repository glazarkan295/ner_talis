"""Конструктор формул (ТЗ 13 §2).

Запись = игровая формула: выражение + переменные + ограничения (min/max,
округление, проценты). Хранение — EntityStore (data/formula_constructor.json).
Включает безопасный вычислитель выражений (ast-whitelist) для функции
«Проверить формулу» — без eval/exec и без доступа к атрибутам/импортам.
"""

from __future__ import annotations

import ast
import math
import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")

# Категории формул (ТЗ §2.4).
FORMULA_CATEGORIES = (
    "exp", "levels", "pve", "pvp", "damage", "defense", "crit", "dodge",
    "accuracy", "heal", "regen", "gather", "drop", "events", "search_depth",
    "craft", "alchemy", "smithing", "smelting", "leatherworking", "jewelry",
    "enchanting", "economy", "fines", "transfer", "referral", "world_events",
    "effects", "curses", "states", "zones", "house", "ratings",
)
FORMULA_CATEGORY_LABELS = {
    "exp": "Опыт", "levels": "Уровни", "pve": "PVE-бой", "pvp": "Будущий PVP",
    "damage": "Урон", "defense": "Защита", "crit": "Критический удар",
    "dodge": "Уклонение", "accuracy": "Точность", "heal": "Лечение",
    "regen": "Регенерация", "gather": "Добыча", "drop": "Дроп",
    "events": "События", "search_depth": "Глубина поиска", "craft": "Ремесло",
    "alchemy": "Алхимия", "smithing": "Кузнечное дело", "smelting": "Плавильное дело",
    "leatherworking": "Кожевенное дело", "jewelry": "Ювелирное дело",
    "enchanting": "Зачарование", "economy": "Экономика", "fines": "Штрафы",
    "transfer": "Передача предметов", "referral": "Реферальная система",
    "world_events": "Мировые события", "effects": "Эффекты", "curses": "Проклятия",
    "states": "Состояния", "zones": "Зоны", "house": "Дом игрока", "ratings": "Рейтинги",
}

ROUNDING_MODES = ("none", "floor", "ceil", "round")
ROUNDING_LABELS = {"none": "Без округления", "floor": "Вниз", "ceil": "Вверх", "round": "Математическое"}

# Стандартный каталог переменных (ТЗ §2.5) — для подсказок и автодополнения.
VARIABLE_CATALOG = (
    {"key": "player_level", "label": "Уровень игрока"},
    {"key": "mob_level", "label": "Уровень моба"},
    {"key": "item_level", "label": "Уровень предмета"},
    {"key": "recipe_level", "label": "Уровень рецепта"},
    {"key": "profession_level", "label": "Уровень профессии"},
    {"key": "quality", "label": "Качество предмета"},
    {"key": "rarity", "label": "Редкость предмета"},
    {"key": "item_count", "label": "Количество предметов"},
    {"key": "mob_count", "label": "Количество мобов"},
    {"key": "resource_count", "label": "Количество ресурсов"},
    {"key": "level_diff", "label": "Разница уровней"},
    {"key": "base_amount", "label": "Базовая сумма"},
    {"key": "base_chance", "label": "Базовый шанс"},
    {"key": "bonus", "label": "Бонус"},
    {"key": "antibonus", "label": "Антибонус"},
    {"key": "multiplier", "label": "Множитель"},
    {"key": "search_depth", "label": "Глубина поиска"},
    {"key": "difficulty", "label": "Сложность рецепта"},
    {"key": "weight", "label": "Вес"},
    {"key": "price", "label": "Цена"},
    {"key": "tax", "label": "Налог"},
    {"key": "commission", "label": "Комиссия"},
)
_CATALOG_KEYS = {v["key"] for v in VARIABLE_CATALOG}

# Разрешённые функции в выражении.
_FUNCS = {
    "min": min, "max": max, "abs": abs, "round": round, "pow": pow,
    "floor": math.floor, "ceil": math.ceil, "sqrt": math.sqrt,
}

_store = EntityStore(
    env_var="FORMULA_CONSTRUCTOR_PATH",
    default_rel="data/formula_constructor.json",
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


# --- Безопасный вычислитель выражений --------------------------------------
class FormulaError(ValueError):
    """Ошибка разбора/вычисления формулы."""


_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
_ALLOWED_CMP = (ast.Lt, ast.Gt, ast.LtE, ast.GtE, ast.Eq, ast.NotEq)


def _declared_variable_keys(data: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    raw = data.get("variables")
    if isinstance(raw, list):
        for row in raw:
            if isinstance(row, dict) and str(row.get("key") or "").strip():
                keys.add(str(row["key"]).strip())
    return keys


def expression_names(expr: str) -> set[str]:
    """Имена (переменные/функции), встречающиеся в выражении."""
    tree = ast.parse(str(expr or ""), mode="eval")
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


def _eval_node(node: ast.AST, env: dict[str, float]) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, env)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise FormulaError("Допустимы только числовые константы.")
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        raise FormulaError(f"Неизвестная переменная: {node.id}")
    if isinstance(node, ast.BinOp) and isinstance(node.op, _ALLOWED_BINOPS):
        left, right = _eval_node(node.left, env), _eval_node(node.right, env)
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            raise FormulaError("Деление на ноль.")
        return _apply_binop(node.op, left, right)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        val = _eval_node(node.operand, env)
        return +val if isinstance(node.op, ast.UAdd) else -val
    if isinstance(node, ast.IfExp):
        return _eval_node(node.body, env) if _eval_node(node.test, env) else _eval_node(node.orelse, env)
    if isinstance(node, ast.BoolOp):
        vals = [_eval_node(v, env) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], _ALLOWED_CMP):
        return _apply_cmp(node.ops[0], _eval_node(node.left, env), _eval_node(node.comparators[0], env))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        if node.keywords:
            raise FormulaError("Именованные аргументы функций не поддерживаются.")
        args = [_eval_node(a, env) for a in node.args]
        return _FUNCS[node.func.id](*args)
    raise FormulaError("Недопустимая конструкция в формуле.")


def _apply_binop(op: ast.AST, a: Any, b: Any) -> Any:
    if isinstance(op, ast.Add):
        return a + b
    if isinstance(op, ast.Sub):
        return a - b
    if isinstance(op, ast.Mult):
        return a * b
    if isinstance(op, ast.Div):
        return a / b
    if isinstance(op, ast.FloorDiv):
        return a // b
    if isinstance(op, ast.Mod):
        return a % b
    if isinstance(op, ast.Pow):
        return a ** b
    raise FormulaError("Недопустимая операция.")


def _apply_cmp(op: ast.AST, a: Any, b: Any) -> bool:
    if isinstance(op, ast.Lt):
        return a < b
    if isinstance(op, ast.Gt):
        return a > b
    if isinstance(op, ast.LtE):
        return a <= b
    if isinstance(op, ast.GtE):
        return a >= b
    if isinstance(op, ast.Eq):
        return a == b
    if isinstance(op, ast.NotEq):
        return a != b
    raise FormulaError("Недопустимое сравнение.")


def evaluate_expression(expr: str, values: dict[str, Any]) -> float:
    """Безопасно вычислить выражение с переданными значениями переменных."""
    env: dict[str, float] = {}
    for k, v in (values or {}).items():
        n = _num(v)
        if n is not None:
            env[str(k)] = n
    try:
        tree = ast.parse(str(expr or ""), mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"Синтаксическая ошибка: {exc.msg}") from exc
    result = _eval_node(tree, env)
    return float(result)


def _apply_constraints(value: float, data: dict[str, Any]) -> tuple[float, list[str]]:
    notes: list[str] = []
    if data.get("is_percent"):
        if value < 0:
            value, _ = 0.0, notes.append("Шанс ограничен снизу до 0%.")
        if value > 100:
            value, _ = 100.0, notes.append("Шанс ограничен сверху до 100%.")
    lo = _num(data.get("min_result"))
    hi = _num(data.get("max_result"))
    if lo is not None and value < lo:
        value = lo
        notes.append(f"Результат поднят до минимума {lo}.")
    if hi is not None and value > hi:
        value = hi
        notes.append(f"Результат опущен до максимума {hi}.")
    if not data.get("allow_negative", True) and value < 0:
        value = 0.0
        notes.append("Отрицательный результат запрещён → 0.")
    rounding = str(data.get("rounding") or "none")
    if rounding == "floor":
        value = math.floor(value)
    elif rounding == "ceil":
        value = math.ceil(value)
    elif rounding == "round":
        value = round(value)
    if not data.get("allow_zero", True) and value == 0:
        notes.append("Ноль не разрешён (предупреждение).")
    return value, notes


def test_formula(data: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    """Прогнать формулу с тестовыми значениями (ТЗ §2.6)."""
    expr = str(data.get("expression") or "").strip()
    if not expr:
        return {"ok": False, "errors": ["Формула пуста."], "result": None}
    env: dict[str, Any] = {}
    for row in (data.get("variables") or []):
        if isinstance(row, dict) and str(row.get("key") or "").strip():
            env[str(row["key"]).strip()] = _num(row.get("default")) or 0
    for k, v in (values or {}).items():
        env[str(k)] = v
    try:
        raw = evaluate_expression(expr, env)
    except FormulaError as exc:
        return {"ok": False, "errors": [str(exc)], "result": None, "resolved": env}
    final, notes = _apply_constraints(raw, data)
    return {"ok": True, "errors": [], "raw_result": raw, "result": final,
            "resolved": env, "notes": notes}


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not str(data.get("name") or "").strip():
        errors.append("Не заполнено название формулы.")
    category = str(data.get("category") or "").strip()
    if category and category not in FORMULA_CATEGORIES:
        warnings.append(f"Категория «{category}» не из стандартного списка.")

    expr = str(data.get("expression") or "").strip()
    if not expr:
        errors.append("Текст формулы не заполнен.")
    else:
        try:
            names = expression_names(expr)
        except SyntaxError as exc:
            names = set()
            errors.append(f"Синтаксическая ошибка в формуле: {exc.msg}")
        else:
            known = _declared_variable_keys(data) | _CATALOG_KEYS | set(_FUNCS)
            for nm in sorted(names):
                if nm not in known:
                    errors.append(f"Неизвестная переменная/функция: {nm}.")
            # Сухой прогон на дефолтах ловит деление на ноль/недопустимые узлы.
            probe = {k: 1 for k in names}
            try:
                evaluate_expression(expr, probe)
            except FormulaError as exc:
                errors.append(str(exc))

    rounding = str(data.get("rounding") or "none")
    if rounding and rounding not in ROUNDING_MODES:
        errors.append(f"Неизвестный режим округления: {rounding}.")
    lo = _num(data.get("min_result"))
    hi = _num(data.get("max_result"))
    if lo is not None and hi is not None and lo > hi:
        errors.append("Минимальный результат больше максимального.")
    if data.get("is_percent"):
        if lo is not None and lo < 0:
            warnings.append("Для шанса минимум обычно ≥ 0.")
        if hi is not None and hi > 100:
            warnings.append("Для шанса максимум обычно ≤ 100.")

    for key in ("name", "short_description", "technical_description"):
        value = str(data.get(key) or "").strip()
        if value and (_HTML_RE.search(value) or "<script" in value.lower()):
            errors.append(f"В поле «{key}» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def where_used(formula_id: str) -> list[dict[str, Any]]:
    """Где используется формула (ТЗ §2.8). Заглушка: связи появятся по мере
    привязки формул в других конструкторах (поле formula_id)."""
    return []
