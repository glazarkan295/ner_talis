# ТЗ для Claude Code: правки V2 city context, publish-прав и search-depth runtime gate

## 0. Назначение файла

Этот файл — отдельное техническое задание для Claude Code по свежему документу **1.2.txt**.

Цель: исправить три важные проблемы проекта **Нер-Талис**:

1. V2 city buttons не должны получать legacy `current_zone/location_id` как V2-контекст.
2. Published blessing/trait/phase/camp update routes должны требовать publish-права перед изменением live-объекта.
3. Настройки глубины поиска из конструктора локаций должны применяться только при включённом V2 location runtime.

---

# 1. Не передавать legacy zones как V2 button context

## 1.1. Проблема

В `ner_talis_game_project/services/city_service.py` при включённом `city_runtime.live_enabled()` текущий V2-узел берётся из:

```python
current_node = str(player.get("current_city_node") or "")
```

Если он отсутствует или не опубликован, код всё ещё делает fallback:

```python
current_node = str(player.get("current_zone") or player.get("location_id") or "")
```

Проблема: `current_zone/location_id` — это legacy-идентификатор, а не обязательно V2 city node.

Если после включения `use_v2_buttons` или `CITY_CONSTRUCTOR_LIVE` у старого игрока есть непустой legacy zone, но это не опубликованный V2 node, `city_runtime.try_handle()` получает непустой `current_node_id`.

Из-за этого `try_handle()` подавляет global button-label fallback, потому что считает, что контекст уже есть.

Итог:

- V2 entry button может не сработать;
- кнопка игнорируется, если label не совпадает с node name;
- игрок не может нормально войти в V2-ветку;
- проблема проявляется особенно у старых игроков после включения V2 runtime.

## 1.2. Требование

В `city_service.py` нельзя передавать legacy `current_zone/location_id` как V2 button context, пока не подтверждено, что это реальный опубликованный V2 city node.

Правило:

```text
current_node_id передаётся в city_runtime.try_handle() только если city_runtime.node_runtime_view(current_node) вернул реальный V2 node.
```

Если подтверждения нет — передавать пустой контекст.

## 1.3. Правильная логика

Нужно сделать примерно так:

```python
current_node = str(player.get("current_city_node") or "")

if current_node and city_runtime.node_runtime_view(current_node) is None:
    current_node = ""

legacy_node = str(player.get("current_zone") or player.get("location_id") or "")

if not current_node and legacy_node:
    if city_runtime.node_runtime_view(legacy_node) is not None:
        current_node = legacy_node
    else:
        current_node = ""

node_response = city_runtime.try_handle(action, current_node_id=current_node)
```

Важно: если `legacy_node` не является V2 node, контекст должен остаться пустым.

## 1.4. Критерии готовности

Готово, если:

- legacy `current_zone/location_id` не передаётся как V2 context без подтверждения через `node_runtime_view`;
- V2 entry buttons работают у старых игроков после включения V2 runtime;
- global button-label fallback не подавляется ложным legacy context;
- кнопка **Назад** работает после перехода в настоящий V2 node;
- legacy routing не сломан;
- есть тест на старого игрока с legacy zone и пустым `current_city_node`.

---

# 2. Требовать publish-права для published blessing edits

## 2.1. Проблема

В `ner_talis_game_project/admin_blessing_api.py` update route для благословений делает:

```python
_require(session, PERM_BLESSING_EDIT)
...
blessings.store().update(...)
```

Если blessing уже опубликован, `EntityStore.update()` сохраняет published-статус.

Итог: content-role admin, у которого есть `blessing.edit`, но нет `blessing.publish`, может изменить live published blessing без publish approval.

## 2.2. Требование

Перед обновлением published blessing нужно проверять старый статус объекта.

Если объект уже `published`, для изменения live-данных требуется `PERM_BLESSING_PUBLISH`.

## 2.3. Правильная логика

Перед update:

```python
before = blessings.store().get(blessing_id)

if before and before.get("status") == "published":
    _require(session, PERM_BLESSING_PUBLISH)
```

Если в проекте уже есть общий helper для published update guard, использовать его, а не дублировать логику.

## 2.4. Распространить правило на аналогичные routes

Аналогичный hand-written pattern используется в routes:

- blessing;
- trait;
- phase;
- camp.

Нужно проверить все ручные update routes, которые работают через `EntityStore.update()` и требуют только `*.edit`.

Для каждого такого route:

- если объект draft — достаточно edit;
- если объект published — нужно publish;
- если доступен draft-overlay — можно создавать черновик вместо live update;
- если draft-overlay пока нет — требовать publish-права.

## 2.5. Критерии готовности

Готово, если:

- published blessing нельзя изменить без `blessing.publish`;
- published trait нельзя изменить без соответствующего publish-права;
- published phase нельзя изменить без соответствующего publish-права;
- published camp нельзя изменить без соответствующего publish-права;
- draft-объекты можно редактировать с edit-правом;
- пользователь без publish-права получает понятную ошибку;
- пользователь с publish-правом может изменить published объект;
- изменения пишутся в audit/history;
- есть тесты на blessing/trait/phase/camp published update без publish-права.

---

# 3. Gate search-depth config behind V2 location flag

## 3.1. Проблема

В `ner_talis_game_project/services/external_location_service.py` `_search_depth_max` читает published V2 location data:

```python
env = wcr.get_content(wcr.KIND_LOCATION, str(location_id))
if isinstance(env, dict) and env.get("status") == "published":
    data = env.get("data") or {}
    if data.get("search_depth_enabled"):
        return int(data.get("search_depth_max") or 0)
```

Проблема: это происходит даже когда `use_v2_locations` или `WORLD_CONSTRUCTOR_LIVE` выключены.

Если админ опубликовал V2 location с `search_depth_enabled`, но V2 runtime выключен, legacy search всё равно получает `search_depth_max`.

Итог:

- флаг V2 locations больше не изолирует runtime;
- legacy search начинает зависеть от constructor data;
- поиск может быть неожиданно ограничен published V2 настройками;
- админ думает, что V2 выключен, но часть V2-логики уже влияет на игру.

## 3.2. Требование

Настройки глубины поиска из конструктора локаций должны применяться только тогда, когда включён V2 location runtime.

Перед чтением V2 registry нужно проверить:

```python
location_runtime.live_enabled()
```

или эквивалентный feature flag, который реально управляет V2 locations.

Если V2 locations выключены — `_search_depth_max` должен возвращать `0` или legacy default и не читать constructor registry.

## 3.3. Правильная логика

Пример:

```python
from services import location_runtime

def _search_depth_max(location_id: str) -> int:
    if not location_runtime.live_enabled():
        return 0

    env = wcr.get_content(wcr.KIND_LOCATION, str(location_id))
    if isinstance(env, dict) and env.get("status") == "published":
        data = env.get("data") or {}
        if data.get("search_depth_enabled"):
            return int(data.get("search_depth_max") or 0)

    return 0
```

Если в проекте используется `use_v2_locations` вместо env-only check, нужно опираться на фактический runtime flag, а не только на UI flag.

## 3.4. Критерии готовности

Готово, если:

- при выключенном V2 location runtime legacy search игнорирует constructor search-depth config;
- published V2 location не влияет на legacy search, если V2 locations выключены;
- при включённом V2 location runtime search-depth работает;
- feature flag действительно изолирует runtime;
- есть тест на выключенный V2 runtime + published V2 location;
- есть тест на включённый V2 runtime + enabled search depth.

---

# 4. Общие тесты

## 4.1. City context tests

Сценарии:

- старый игрок имеет `current_zone`, но не имеет `current_city_node`;
- `current_zone` не является V2 node;
- V2 entry button должен сработать через global fallback;
- после перехода сохраняется `current_city_node`;
- следующая кнопка **Назад** работает в контексте V2 node.

## 4.2. Published update permission tests

Сценарии:

- blessing draft update с edit-правом проходит;
- blessing published update без publish-права запрещён;
- blessing published update с publish-правом проходит;
- аналогично для trait;
- аналогично для phase;
- аналогично для camp.

## 4.3. Search depth runtime gate tests

Сценарии:

- V2 locations выключены, published V2 location имеет search depth, legacy search не ограничивается;
- V2 locations включены, published V2 location имеет search depth, cap применяется;
- V2 location draft/disabled, cap не применяется;
- V2 location published, но `search_depth_enabled=false`, cap не применяется.

---

# 5. Общие критерии готовности

Задача считается выполненной, если:

- V2 city runtime не получает legacy zone/location_id как контекст без подтверждения;
- V2 entry buttons работают после включения V2 у старых игроков;
- published blessing/trait/phase/camp нельзя менять без publish-права;
- draft objects редактируются с edit-правом;
- search-depth config из конструктора применяется только при включённом V2 location runtime;
- legacy search изолирован от V2 constructor data при выключенных флагах;
- добавлены тесты на все исправления;
- ошибки API возвращаются понятно и на русском языке;
- исправления не ломают legacy runtime.
