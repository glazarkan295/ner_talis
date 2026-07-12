# ТЗ для Claude Code: правки импорта, публикации world/entity объектов и invalid effect seeds

## 0. Назначение файла

Этот файл — отдельное техническое задание для Claude Code по свежему документу **1.2.txt**.

Цель: исправить проблемы в импорте, публикации live-данных, редактировании связей через интерактивную схему и обработке невалидных seed-эффектов в проекте **Нер-Талис**.

Правки относятся к следующим зонам:

- legacy world import endpoint;
- `constructor_import`;
- публикация мобов после overwrite-import;
- `admin_graph_service`;
- права publish для EntityStore-источников;
- обработка invalid effect seeds.

---

# 1. Legacy world import не должен запускать все импортеры при пустом selected

## 1.1. Проблема

В `admin_world_api.py` legacy-эндпоинт:

```text
/api/admin/v2/world/import
```

ограничен только world-типами:

```python
world_kinds = ("item", "mob", "location", "event")
selected = [k for k in (payload.kinds or world_kinds) if k in world_kinds]
```

Если клиент отправляет только запрещённые или ошибочные kinds, например:

```json
{
  "kinds": ["achievement"]
}
```

или:

```json
{
  "kinds": ["achievment"]
}
```

то `selected == []`.

Дальше `constructor_import.import_all()` воспринимает пустой список как отсутствие фильтра и запускает все импортеры:

```python
kinds or list(IMPORTERS)
```

Итог: legacy world endpoint неожиданно запускает импорт всего проекта.

## 1.2. Требование

Нужно разделить два случая:

### Случай A — клиент не передал kinds

Если `payload.kinds` пустой или отсутствует, legacy endpoint может использовать world default:

```python
("item", "mob", "location", "event")
```

### Случай B — клиент передал kinds, но все они отфильтрованы

Если пользователь явно передал kinds, но после фильтрации список пустой, нужно вернуть ошибку `400`, а не запускать все импортеры.

## 1.3. Что сделать

Нужно изменить логику так:

```python
requested = payload.kinds

if requested is None or requested == []:
    selected = list(world_kinds)
else:
    selected = [k for k in requested if k in world_kinds]
    if not selected:
        raise HTTPException(
            status_code=400,
            detail="Legacy world import поддерживает только: item, mob, location, event."
        )
```

Важно:

- не передавать `[]` в `constructor_import.import_all()`, если это означает “ничего не импортировать”;
- `None` передавать только тогда, когда реально нужен default;
- для legacy world endpoint лучше передавать именно `selected`, а не `None`, чтобы endpoint не вышел за world-область.

## 1.4. Критерии готовности

Готово, если:

- `/api/admin/v2/world/import` без `kinds` импортирует только world-типы;
- `/api/admin/v2/world/import` с `["item", "mob"]` импортирует только item/mob;
- `/api/admin/v2/world/import` с `["achievement"]` возвращает 400;
- `/api/admin/v2/world/import` с ошибочным kind возвращает 400;
- endpoint не запускает все импортеры при `selected == []`;
- есть тест на disallowed kind;
- есть тест на misspelled kind.

---

# 2. Republish mobs после overwrite imports

## 2.1. Проблема

В `constructor_import.py` при update/overwrite уже опубликованного импортированного моба вызывается:

```python
wcr.update_content(wcr.KIND_MOB, sid, data, actor=actor)
```

Но `wcr.update_content()` переводит опубликованный world content обратно в draft.

После re-import обновлённые мобы исчезают из runtime-путей, которые читают только published world content.

## 2.2. Требование

После overwrite-import опубликованного импортированного моба нужно вернуть его в published, если данные валидны.

Логика должна соответствовать `_apply_record`, где после обновления world records используется republish step.

## 2.3. Что сделать

При overwrite imported mob:

- определить, был ли existing объект published до обновления;
- выполнить update;
- проверить валидность mob data;
- если объект был published и данные валидны — снова опубликовать;
- если данные невалидны — оставить draft/error и добавить в `needs_check`;
- если объект был draft — не публиковать автоматически без причины;
- если overwrite заблокирован ручными правками — не менять объект и не публиковать.

## 2.4. Критерии готовности

Готово, если:

- опубликованный imported mob после overwrite-import остаётся published, если данные валидны;
- mob не исчезает из live runtime после re-import;
- невалидный mob не публикуется автоматически;
- blocked/manual-edited mob не перезаписывается;
- отчёт импорта показывает, что было updated/republished/needs_check;
- есть тест: published imported mob + overwrite остаётся published.

---

# 3. Graph edits для EntityStore-источников должны требовать publish-права

## 3.1. Проблема

В `admin_graph_service.py` для EntityStore-источников, например:

- recipe;
- workshop;
- workshop_message;
- formula;
- race;
- profession;
- другие constructor sources,

редактирование связи идёт через:

```python
svc.store().update(entity_id, data, actor=actor)
```

Endpoint требует только `graph.edit`.

Так как `EntityStore.update()` сохраняет published-статус, пользователь с `graph.edit`, но без соответствующего `*.publish`, может изменить live recipe/workshop relation.

## 3.2. Требование

Для EntityStore-источников нужно применить такой же published-status guard, как для world nodes.

Если source-объект опубликован, graph edit не должен менять live-версию без publish-права.

## 3.3. Возможные варианты реализации

### Вариант A — требовать publish-права

Перед `svc.store().update()`:

- проверить статус объекта;
- если статус `published`, определить нужное publish permission;
- если у пользователя нет publish permission — вернуть ошибку.

### Вариант B — создавать draft overlay

Если инфраструктура draft/publish поддерживается:

- graph edit опубликованного объекта создаёт черновую версию;
- live-версия остаётся без изменений;
- схема показывает, что связь изменена в черновике;
- публикация требует publish-права.

Предпочтительный вариант: **draft overlay**, если он уже поддержан. Если нет — строгая проверка publish-права.

## 3.4. Как определить publish permission

Нужно добавить маппинг:

```text
recipe -> craft.publish / recipes.publish
workshop -> craft.publish / workshops.publish
workshop_message -> craft.publish / workshop_messages.publish
formula -> formulas.publish
race -> races.publish
profession -> craft.publish / professions.publish
```

Или использовать существующую систему permission metadata, если она уже есть.

Важно: не хардкодить непонятные права без связи с текущей RBAC-моделью проекта.

## 3.5. Критерии готовности

Готово, если:

- `graph.edit` сам по себе не даёт право менять published EntityStore live-сущности;
- published recipe нельзя изменить через схему без publish-права;
- published workshop нельзя изменить через схему без publish-права;
- published workshop_message нельзя изменить через схему без publish-права;
- пользователь с нужным publish-правом может изменить связь;
- пользователь без publish-права получает понятную ошибку;
- изменение пишется в историю;
- есть тест на published EntityStore source + graph edit без publish-права.

---

# 4. Invalid effect seeds при overwrite должны уходить в draft/error

## 4.1. Проблема

В `constructor_import.py` при overwrite существующего effect seed:

```python
store.update(effect_id, data, actor=actor)
_publish_if_valid(effect_id, data)
```

Если seed уже был импортирован и опубликован до появления новой валидации, `EntityStore.update()` сохраняет published-статус.

Если `_publish_if_valid()` возвращает false, объект всё равно остаётся published, потому что update не меняет статус.

Итог: невалидные seed-эффекты, например `slow` или `stun`, могут оставаться live после re-import.

## 4.2. Требование

Если effect seed после overwrite не проходит валидацию, он должен быть понижен из published в draft/error и попасть в `needs_check`.

Нельзя оставлять invalid seed live.

## 4.3. Что сделать

При overwrite existing effect seed:

- сохранить старый статус;
- обновить данные, если не blocked;
- выполнить валидацию;
- если валидно:
  - publish или оставить published;
- если невалидно:
  - перевести в draft/error;
  - добавить в `needs_check`;
  - показать в отчёте импорта;
  - не оставлять published.
- если объект был вручную изменён и overwrite заблокирован:
  - не обновлять;
  - не менять статус;
  - отметить как skipped/blocked.

## 4.4. Требования к статусам

Если в системе есть только статусы:

- draft;
- published;
- disabled;
- archived;

то invalid seed переводить в `draft` и добавлять ошибку в validation report.

Если есть статус:

- error;
- needs_check;
- invalid;

использовать более точный статус.

В любом случае invalid effect не должен оставаться published.

## 4.5. Отчёт импорта

Отчёт должен показывать:

- сколько эффектов обновлено;
- сколько опубликовано;
- сколько оставлено в draft;
- сколько переведено из published в draft/error;
- какие эффекты требуют проверки;
- почему эффект невалиден;
- какие поля нужно исправить.

## 4.6. Критерии готовности

Готово, если:

- invalid existing seed после overwrite не остаётся published;
- invalid seed попадает в `needs_check`;
- valid seed публикуется корректно;
- blocked/manual-edited seed не затирается;
- отчёт импорта показывает invalid seeds;
- есть тест: ранее published invalid seed после overwrite становится draft/error.

---

# 5. Общие требования к тестам

Нужно добавить или обновить тесты.

## 5.1. World import filtered kinds

- без kinds импортирует item/mob/location/event;
- с allowed kinds импортирует только их;
- с disallowed kind возвращает 400;
- с misspelled kind возвращает 400;
- `selected == []` не запускает все importers.

## 5.2. Mob overwrite republish

- published imported mob после overwrite остаётся published;
- invalid mob не публикуется;
- blocked mob не обновляется;
- runtime видит mob после re-import.

## 5.3. Graph EntityStore publish guard

- graph.edit без publish не меняет published recipe;
- graph.edit без publish не меняет published workshop;
- graph.edit без publish не меняет published workshop_message;
- пользователь с publish может изменить;
- история изменений создаётся.

## 5.4. Invalid effect seeds

- previously published invalid seed после overwrite становится draft/error;
- valid seed остаётся/становится published;
- invalid seed попадает в needs_check;
- blocked seed не меняется.

---

# 6. Общие критерии готовности

Задача считается выполненной, если:

- legacy world import больше не запускает все импортеры при пустом selected после фильтрации;
- disallowed/misspelled kinds возвращают понятную 400-ошибку;
- published imported mobs после overwrite не исчезают из live runtime;
- graph edits для EntityStore-источников защищены publish-правами или draft-overlay;
- invalid effect seeds не остаются published после overwrite;
- отчёты импорта показывают skipped/blocked/republished/needs_check;
- все ошибки в админ-панели выводятся на русском языке;
- добавлены тесты для всех исправлений.
