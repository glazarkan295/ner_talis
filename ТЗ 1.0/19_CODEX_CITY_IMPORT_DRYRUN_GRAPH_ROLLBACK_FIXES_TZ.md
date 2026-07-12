# ТЗ для Claude Code: правки city publish, dry-run, V2 routing, graph kinds и rollback

## 0. Задача

Подготовить и внедрить правки по замечаниям из `1.2.txt` для проекта **Нер-Талис**.

Нужно исправить:

1. редактирование опубликованных city records без `city.publish`;
2. изменение данных во время dry-run импорта достижений;
3. неправильный переход по дочерним V2 city nodes с одинаковыми названиями;
4. схлопывание разных `_kind` city constructor records в один тип `city` на интерактивной схеме;
5. удаление вручную изменённых imported records при rollback.

---

# 1. Требовать publish-права перед редактированием live city records

## Проблема

В `admin_city_api.py` update path требует только `city.edit`, а затем вызывает `city.store().update(...)`.

Если city record уже опубликован, `EntityStore.update()` сохраняет published-статус. Поэтому роль с `city.edit`, но без `city.publish`, может менять live V2 city records.

Это касается:

- `city_node`;
- `city_button`;
- `city_shop_item`;
- переходов;
- текстов;
- сервисов;
- других city constructor records.

## Требование

Перед update нужно проверить старый статус.

Если объект `published`, требовать `city.publish`.

Пример:

```python
before = city.store().get(city_id)

if before and before.get("status") == "published":
    _require(session, PERM_CITY_PUBLISH)
```

Если есть draft-overlay, можно создавать черновик для роли с `city.edit`, но live published object нельзя менять без `city.publish`.

## Критерии готовности

- Published city record нельзя изменить только с `city.edit`.
- Draft city record можно изменить с `city.edit`.
- Published city record можно изменить с `city.publish`.
- Действие пишется в audit/history.
- Ошибка прав показывается на русском.
- Есть тест на published city update без `city.publish`.

---

# 2. Achievement setup не должен менять данные во время dry-run

## Проблема

В `constructor_import.py` dry-run импорта достижений может создать и опубликовать категорию `small_plateau`, потому что setup-блок находится вне dry-run guards.

Итог: `/api/admin/v2/import/dry-run` мутирует `data/achievement_categories.json`, хотя должен только показывать план изменений.

## Требование

Dry-run не должен менять данные.

Во время dry-run нельзя:

- создавать category;
- публиковать category;
- менять `achievement_categories.json`;
- менять store;
- менять статусы.

## Что сделать

В setup достижений добавить dry-run guard.

Варианты:

```python
if dry_run:
    report_planned_category_setup("small_plateau")
else:
    cats.create(...)
    cats.set_status(...)
```

или заменить `cats.create/set_status` на no-op при dry-run.

## Критерии готовности

- Achievement dry-run не создаёт `small_plateau`.
- Achievement dry-run не публикует category.
- Real run создаёт category, если нужно.
- Dry-run report показывает planned changes.
- Есть тест: dry-run не меняет файл/хранилище.

---

# 3. Резолвить child-node clicks внутри текущего parent

## Проблема

В `city_runtime.py` V2 city nodes могут auto-render child names as buttons.

Текущий global lookup через `node_by_name.get(act)` игнорирует `current_node_id`.

Если у двух разных родителей есть дочерний узел с одинаковым названием, например:

- Район 1 → `Таверна`;
- Район 2 → `Таверна`;

то кнопка `Таверна` может открыть первый найденный global node, а не child текущего parent.

## Требование

Порядок резолва должен быть таким:

1. кнопка-переход на текущем узле;
2. child node текущего parent с таким display name;
3. global node name lookup;
4. global button fallback, если он допустим.

Пример:

```python
target = _button_target_on_node(current_node_id, act)

if not target and current_node_id:
    target = _child_node_by_name(parent_id=current_node_id, label=act)

if not target:
    node_by_name, button_to_target = _published_label_index()
    target = node_by_name.get(act)

if not target:
    target = button_to_target.get(act)
```

## Критерии готовности

- `Таверна` внутри parent A открывает child A.
- `Таверна` внутри parent B открывает child B.
- Одинаковые названия child nodes не конфликтуют.
- Global fallback работает только после context child lookup.
- Есть тест на два parent nodes с одинаковым child display name.

---

# 4. Preserve city constructor kinds in graph

## Проблема

В `admin_graph_service.py` `city_constructor_service` зарегистрирован как единый node type:

```python
("city", "city_constructor_service", "city_name")
```

Но в store есть разные реальные `_kind`:

- `city_node`;
- `city_button`;
- `city_shop_item`;
- другие city-specific kinds.

Сейчас graph схлопывает их в type `city`, поэтому:

- `city_node:<id>` не находится;
- `city_button:<id>` не находится;
- parent/button/shop связи не отображаются корректно;
- интерактивная схема теряет структуру V2 city.

## Требование

Сохранять реальные `_kind` в graph.

Нужно поддерживать отдельные node types:

- `city_node`;
- `city_button`;
- `city_shop_item`;
- `city_transition`, если есть;
- `city_npc`, если есть;
- `city_service`, если есть.

## Варианты реализации

### Вариант A

В `_constructor_nodes` брать тип из `data._kind`:

```python
node_type = data.get("_kind") or "city"
```

### Вариант B

Сделать отдельный city-specific extractor, который строит:

- city nodes;
- city buttons;
- shop items;
- parent-child edges;
- button target edges;
- shop item/item edges;
- NPC/service edges.

Предпочтительно использовать city-specific extractor, если нужна точная схема.

## Критерии готовности

- Graph API возвращает `city_node:<id>`.
- Graph API возвращает `city_button:<id>`.
- Graph API возвращает `city_shop_item:<id>`.
- City records не схлопываются все в `city`.
- Схема показывает parent-child связи.
- Схема показывает button → target связи.
- Схема показывает shop item связи.
- Есть тест на store с несколькими `_kind`.

---

# 5. Rollback не должен удалять imported records, которые админ уже изменил

## Проблема

Rollback импорта удаляет journaled EntityStore record, если `data.imported == true`.

Но обычные constructor edits сохраняют `data.imported`, потому что данные merge-ятся с existing data.

Сценарий:

1. Админ импортирует record.
2. Record получает `imported=true`.
3. Админ вручную редактирует record.
4. `imported=true` остаётся.
5. Rollback последнего импорта удаляет record.
6. Ручные правки теряются.

## Требование

Rollback не должен удалять imported records, которые были изменены администратором после импорта.

Такие записи должны считаться:

- `manual_override`;
- `taken_under_control`;
- detached from import.

## Варианты исправления

### Вариант A — очищать import marker при ручном редактировании

При manual edit:

```python
data.imported = false
data.import_source = "manual"
data.manual_override = true
data.import_detached_at = now
data.import_detached_by = actor
```

### Вариант B — сравнивать metadata

Rollback проверяет:

- import run id;
- imported_at;
- last_modified_at;
- last_modified_by;
- last_imported_at;
- import batch id.

Если запись изменена после импорта не import-actor, rollback её не удаляет.

### Вариант C — checksum

При импорте сохранить checksum. При rollback удалить только если текущий checksum совпадает с imported checksum.

Минимально допустимо: вариант A. Лучше: B + C.

## Критерии готовности

- Imported record без ручных правок удаляется rollback.
- Imported record с ручными правками не удаляется rollback.
- Manual edit снимает imported marker или ставит `manual_override`.
- Rollback report показывает `skipped_manual_changed`.
- Ручные правки не теряются.
- Есть тест: import → manual edit → rollback не удаляет record.

---

# 6. Общие тесты

Нужно добавить тесты:

## City publish rights

- published `city_node` update без `city.publish` запрещён;
- published `city_button` update без `city.publish` запрещён;
- published `city_shop_item` update без `city.publish` запрещён;
- draft city record update с `city.edit` разрешён;
- published update с `city.publish` разрешён.

## Achievement dry-run

- dry-run не создаёт category;
- dry-run не публикует category;
- real run создаёт category;
- report показывает planned setup.

## V2 child routing

- два parent nodes имеют child `Таверна`;
- click `Таверна` внутри parent A открывает child A;
- click `Таверна` внутри parent B открывает child B.

## City graph kinds

- store содержит `_kind=city_node`, graph возвращает `city_node:<id>`;
- store содержит `_kind=city_button`, graph возвращает `city_button:<id>`;
- graph показывает parent/button/shop edges.

## Rollback manual override

- imported record удаляется rollback, если не менялся;
- imported record не удаляется rollback, если был manual edit;
- rollback report показывает `skipped_manual_changed`.

---

# 7. Общие критерии готовности

Задача считается выполненной, если:

- published city records защищены `city.publish`;
- achievement dry-run не меняет данные;
- V2 child-node clicks резолвятся в контексте текущего parent;
- city graph сохраняет реальные `_kind`;
- интерактивная схема показывает `city_node`, `city_button`, `city_shop_item` отдельно;
- rollback не удаляет импортированные записи с ручными правками;
- отчёты dry-run/rollback показывают понятные статусы;
- ошибки отображаются на русском языке;
- добавлены тесты на все исправления.
