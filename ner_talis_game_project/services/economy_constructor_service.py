"""Глобальный конструктор экономики ТЗ 2.0.

Опубликованный профиль является единым источником валют, комиссий, глобальных
множителей и защитных лимитов. Доменные сервисы могут читать его через
``active_profile`` без зависимости от API админ-панели.
"""
from __future__ import annotations

from typing import Any
import json

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403

CURRENCY_CODES = ("copper", "silver", "gold", "magic_gold", "ancient_coin")
PRICE_MODES = ("fixed", "formula", "dynamic", "supply_demand")

_store = EntityStore(env_var="ECONOMY_CONSTRUCTOR_PATH", default_rel="data/economy_constructor.json",
                     statuses=STATUSES, transitions=TRANSITIONS, initial_status=STATUS_DRAFT)  # noqa: F405

def store() -> EntityStore:
    return _store

def _num(value: Any) -> float | None:
    try: return float(value)
    except (TypeError, ValueError): return None

def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}; errors: list[str] = []; warnings: list[str] = []
    if not str(data.get("name") or "").strip(): errors.append("Не заполнено название экономического профиля.")
    currencies = data.get("currencies") or []
    codes: set[str] = set()
    for i, row in enumerate(currencies, 1):
        if not isinstance(row, dict): errors.append(f"Валюта #{i}: неверный формат."); continue
        code = str(row.get("code") or "").strip()
        if not code: errors.append(f"Валюта #{i}: не указан код.")
        elif code in codes: errors.append(f"Валюта #{i}: код {code} повторяется.")
        codes.add(code)
        rate = _num(row.get("copper_rate"))
        if rate is None or rate <= 0: errors.append(f"Валюта #{i}: курс к меди должен быть больше нуля.")
        for key, label in (("min_value", "минимум"), ("max_value", "максимум")):
            if row.get(key) not in (None, "") and _num(row.get(key)) is None:
                errors.append(f"Валюта #{i}: {label} должен быть числом.")
        if _num(row.get("max_value")) and _num(row.get("min_value")) is not None and _num(row.get("max_value")) < _num(row.get("min_value")):
            errors.append(f"Валюта #{i}: максимум меньше минимума.")
    for i, row in enumerate(data.get("exchange_rates") or [], 1):
        if not isinstance(row, dict): errors.append(f"Курс обмена #{i}: неверный формат."); continue
        source, target = str(row.get("source_currency") or ""), str(row.get("target_currency") or "")
        if not source or not target or source == target: errors.append(f"Курс обмена #{i}: нужны разные исходная и целевая валюты.")
        if codes and (source not in codes or target not in codes): errors.append(f"Курс обмена #{i}: валюта отсутствует в справочнике.")
        if not row.get("formula_id") and (_num(row.get("rate")) is None or _num(row.get("rate")) <= 0): errors.append(f"Курс обмена #{i}: курс должен быть больше нуля.")
        if row.get("commission_percent") not in (None, "") and (_num(row.get("commission_percent")) is None or not 0 <= _num(row.get("commission_percent")) <= 100): errors.append(f"Курс обмена #{i}: комиссия должна быть 0–100%.")
    market_ids: set[str] = set()
    for i, row in enumerate(data.get("markets") or [], 1):
        if not isinstance(row, dict): errors.append(f"Рынок #{i}: неверный формат."); continue
        market_id = str(row.get("market_id") or "").strip()
        if not market_id: errors.append(f"Рынок #{i}: не указан ID.")
        elif market_id in market_ids: errors.append(f"Рынок #{i}: ID {market_id} повторяется.")
        market_ids.add(market_id)
        items = row.get("items") or []
        if isinstance(items, str):
            try: items = json.loads(items)
            except json.JSONDecodeError: errors.append(f"Рынок #{i}: ассортимент содержит некорректный JSON."); items=[]
        if not isinstance(items, (list, dict)): errors.append(f"Рынок #{i}: ассортимент должен быть списком."); continue
        for j, product in enumerate(items.values() if isinstance(items, dict) else items, 1):
            if not isinstance(product, dict) or not str(product.get("item_id") or product.get("id") or "").strip(): errors.append(f"Рынок #{i}, товар #{j}: не указан предмет.")
            elif product.get("buy_price") not in (None, "") and (_num(product.get("buy_price")) is None or _num(product.get("buy_price")) < 0): errors.append(f"Рынок #{i}, товар #{j}: цена покупки должна быть неотрицательной.")
    for key, label in (("global_buy_multiplier", "Множитель покупки"), ("global_sell_multiplier", "Множитель продажи"),
                       ("reward_multiplier", "Множитель наград"), ("drop_value_multiplier", "Множитель ценности дропа")):
        if data.get(key) not in (None, "") and (_num(data.get(key)) is None or _num(data.get(key)) < 0):
            errors.append(f"{label} должен быть неотрицательным.")
    for key, label in (("market_commission_percent", "Рыночная комиссия"), ("auction_commission_percent", "Комиссия аукциона"),
                       ("delivery_commission_percent", "Комиссия доставки")):
        if data.get(key) not in (None, "") and (_num(data.get(key)) is None or not 0 <= _num(data.get(key)) <= 100):
            errors.append(f"{label} должна быть 0–100%.")
    pavilion = data.get("pavilion") or []
    if isinstance(pavilion, dict): pavilion = [pavilion]
    for i, row in enumerate(pavilion, 1):
        if not isinstance(row, dict): errors.append(f"Павильон #{i}: неверный формат."); continue
        for key, label in (("rent_seconds","срок аренды"),("rent_cost","стоимость аренды"),("item_limit","лимит товаров"),("price_limit","лимит цены")):
            if row.get(key) not in (None, "") and (_num(row.get(key)) is None or _num(row.get(key)) < 0): errors.append(f"Павильон #{i}: {label} должен быть неотрицательным.")
        if row.get("commission_percent") not in (None, "") and (_num(row.get("commission_percent")) is None or not 0 <= _num(row.get("commission_percent")) <= 100): errors.append(f"Павильон #{i}: комиссия должна быть 0–100%.")
    for i,row in enumerate(data.get("casinos") or [],1):
        if not isinstance(row,dict):errors.append(f"Казино #{i}: неверный формат.");continue
        if not str(row.get("casino_id") or "").strip():errors.append(f"Казино #{i}: не указан ID казино.")
        for key,label in (("min_bet","минимальная ставка"),("max_bet","максимальная ставка"),("win_multiplier","множитель выигрыша"),("game_limit","лимит ставок"),("win_limit","лимит выигрыша"),("weekly_limit","недельный лимит")):
            if row.get(key) not in (None,"") and (_num(row.get(key)) is None or _num(row.get(key))<0):errors.append(f"Казино #{i}: {label} должен быть неотрицательным.")
        if _num(row.get("max_bet")) is not None and _num(row.get("min_bet")) is not None and _num(row.get("max_bet"))<_num(row.get("min_bet")):errors.append(f"Казино #{i}: максимальная ставка меньше минимальной.")
        for key,label in (("win_chance","шанс выигрыша"),("commission_percent","комиссия"),("fine_risk","риск штрафа")):
            if row.get(key) not in (None,"") and (_num(row.get(key)) is None or not 0<=_num(row.get(key))<=100):errors.append(f"Казино #{i}: {label} должен быть 0–100%.")
    for i,row in enumerate(data.get("money_caps") or [],1):
        if not isinstance(row,dict):errors.append(f"Лимит денежной массы #{i}: неверный формат.");continue
        if _num(row.get("amount") or row.get("limit")) is None or _num(row.get("amount") or row.get("limit"))<=0:errors.append(f"Лимит денежной массы #{i}: сумма должна быть больше нуля.")
        if str(row.get("period") or "") not in {"","day","daily","week","weekly","month","monthly"}:errors.append(f"Лимит денежной массы #{i}: неизвестный период.")
    for i,row in enumerate(data.get("commissions") or [],1):
        if not isinstance(row,dict):errors.append(f"Комиссия #{i}: неверный формат.");continue
        if not str(row.get("commission_id") or "").strip():errors.append(f"Комиссия #{i}: не указан ID.")
        if row.get("percent") not in (None,"") and (_num(row.get("percent")) is None or not 0<=_num(row.get("percent"))<=100):errors.append(f"Комиссия #{i}: процент должен быть 0–100%.")
        for key,label in (("fixed_amount","фиксированная сумма"),("min","минимум"),("max","максимум")):
            if row.get(key) not in (None,"") and (_num(row.get(key)) is None or _num(row.get(key))<0):errors.append(f"Комиссия #{i}: {label} должна быть неотрицательной.")
    if not currencies: warnings.append("Не задан справочник валют.")
    if data.get("enabled") and not data.get("price_formula_id"): warnings.append("Активный профиль не содержит глобальной формулы цены.")
    from services.formula_runtime import validate_references
    formula_fields=("price_formula_id","reward_formula_id")
    errors.extend(validate_references(data,formula_fields))
    for collection in ("exchange_rates","price_rules","delivery_rules","commissions","services","rewards","dynamic_rules"):
        for row in data.get(collection) or []:
            if isinstance(row,dict):errors.extend(validate_references(row,tuple(key for key in ("formula_id","cost_formula_id","time_formula_id") if row.get(key))))
    used_currencies={str(data.get(key) or "") for key in ("default_currency",)}
    for collection in ("exchange_rates","price_rules","delivery_rules","commissions","services","rewards","casinos"):
        for row in data.get(collection) or []:
            if not isinstance(row,dict):continue
            used_currencies.update(str(row.get(key) or "") for key in ("currency","source_currency","target_currency","buy_currency","sell_currency"))
    for code in codes-used_currencies-{"copper"}:warnings.append(f"Валюта «{code}» создана, но нигде не используется.")
    for i,market in enumerate(data.get("markets") or [],1):
        if not isinstance(market,dict):continue
        if market.get("active",True) and market.get("player_available") is False:warnings.append(f"Рынок #{i} опубликован, но недоступен игрокам.")
        products=market.get("items") or []
        if isinstance(products,str):
            try:products=json.loads(products)
            except json.JSONDecodeError:products=[]
        if isinstance(products,dict):products=list(products.values())
        for j,row in enumerate(products if isinstance(products,list) else [],1):
            if not isinstance(row,dict):continue
            chance=_num(row.get("appearance_chance") if row.get("appearance_chance") not in (None,"") else row.get("chance"))
            if chance is not None and not 0<=chance<=100:errors.append(f"Рынок #{i}, товар #{j}: шанс появления должен быть 0–100%.")
            if row.get("active",True) and not row.get("use_base_price") and not row.get("price_formula_id") and _num(row.get("buy_price")) in (None,0):warnings.append(f"Рынок #{i}, товар #{j}: товар имеет нулевую цену.")
    for i,row in enumerate(data.get("delivery_rules") or [],1):
        if isinstance(row,dict) and row.get("enabled") and not any(row.get(key) not in (None,"",0) for key in ("base_cost","item_cost","stack_cost","cost_formula_id")):errors.append(f"Доставка #{i}: включена, но не задана цена или формула.")
    for i,row in enumerate(data.get("services") or [],1):
        if isinstance(row,dict) and _num(row.get("price")) and not str(row.get("error_text") or "").strip():warnings.append(f"Услуга #{i}: платная, но не задан текст ошибки нехватки денег.")
    for i,row in enumerate(data.get("commissions") or [],1):
        if isinstance(row,dict) and (_num(row.get("percent")) or 0)>30:warnings.append(f"Комиссия #{i}: значение выше 30%, проверьте баланс.")
    return {"ok": not errors, "errors": errors, "warnings": warnings}

def active_profile() -> dict[str, Any]:
    items = store().list(status=STATUS_PUBLISHED)  # noqa: F405
    enabled = [x for x in items if (x.get("data") or {}).get("enabled", True)]
    if not enabled: return {}
    enabled.sort(key=lambda x: (int((x.get("data") or {}).get("priority") or 0), str(x.get("updated_at") or "")), reverse=True)
    return dict(enabled[0].get("data") or {})

def validate_update(before: dict[str, Any], new_data: dict[str, Any]) -> None:
    """Published nested economic IDs are disabled, never silently deleted."""
    if str(before.get("status") or "") != STATUS_PUBLISHED:  # noqa: F405
        return
    old = before.get("data") or {}
    specs = (("currencies", ("code", "currency_id"), "валюту"), ("markets", ("market_id", "id"), "рынок"),
             ("exchange_rates", ("rate_id", "id"), "курс обмена"), ("price_rules", ("rule_id", "id"), "правило цены"),
             ("delivery_rules", ("rule_id", "id"), "правило доставки"), ("commissions", ("commission_id", "id"), "комиссию"),
             ("services", ("service_id", "id"), "услугу"), ("rewards", ("reward_id", "id"), "правило награды"),
             ("casinos", ("casino_id", "id"), "экономику казино"))
    for collection, keys, label in specs:
        def ids(data):
            return {next((str(row.get(key) or "").strip() for key in keys if str(row.get(key) or "").strip()), "")
                    for row in data.get(collection) or [] if isinstance(row, dict)} - {""}
        removed = ids(old) - ids(new_data)
        if removed:
            raise ValueError(f"Нельзя удалить опубликованный объект «{label}»: {', '.join(sorted(removed))}. Отключите запись, сохранив её ID.")

def preview(data: dict[str, Any]) -> dict[str, Any]:
    return {"title": data.get("name") or "Экономический профиль", "enabled": bool(data.get("enabled")),
            "currencies": data.get("currencies") or [], "multipliers": {k: data.get(k) for k in
            ("global_buy_multiplier", "global_sell_multiplier", "reward_multiplier", "drop_value_multiplier")},
            "commissions": {k: data.get(k) for k in ("market_commission_percent", "auction_commission_percent", "delivery_commission_percent")}}
