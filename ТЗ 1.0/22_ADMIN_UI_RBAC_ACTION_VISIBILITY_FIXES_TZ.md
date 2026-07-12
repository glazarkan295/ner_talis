# ТЗ для Claude Code: правки админ UI/RBAC — import buttons, global search, profile-open и rollback

## 0. Назначение файла

Этот файл — отдельное техническое задание для Claude Code по исправлению UI/RBAC-проблем в админ-панели V2 проекта **Нер-Талис**.

Нужно исправить ситуации, когда frontend показывает администратору кнопки/действия, на которые у него нет backend-доступа или для которых backend route вообще не зарегистрирован. Сейчас такие действия приводят к `403`, `404` или `405`, а `requestAdminJson` может воспринимать `403` как истёкшую сессию и очищать admin session token.

Главная цель:

- не показывать недоступные действия;
- не разлогинивать администратора из-за обычного отказа в правах;
- синхронизировать UI с backend permissions/routes;
- сделать поведение понятным и безопасным.

---

# 1. Скрыть «Импортировать библиотеку» для конструкторов без import route

## 1.1. Проблема

В `web/src/components/admin-shell/sections/LibrarySection.jsx` кнопка:

```text
Импортировать библиотеку
```

показывается всем, у кого есть `can.publish`.

Но часть generic `LibrarySection` подключена к factory routers, где backend route:

```text
POST /api/admin/v2/${base}/import
```

регистрируется только если при создании router был передан `import_fn_name`.

Для конструкторов без import function, например:

- formulas;
- professions;
- workshops;
- PVP/combat;
- NPC allies;
- другие generic-конструкторы,

frontend всё равно показывает кнопку импорта и отправляет запрос на несуществующий endpoint.

Итог:

- пользователь видит действие, которое не поддерживается;
- запрос получает `404` или `405`;
- UI выглядит сломанным;
- администратор не понимает, импорт есть или нет.

## 1.2. Требование

Кнопка **Импортировать библиотеку** должна отображаться только если конструктор явно поддерживает импорт.

Нужно добавить явный флаг в config секции:

```js
supportsImport: true
```

или использовать capabilities от backend.

Не считать наличие `can.publish` достаточным условием для показа импорта.

## 1.3. Правильная логика frontend

В `LibrarySection.jsx` заменить условие:

```jsx
{can.publish ? <button>Импортировать библиотеку</button> : null}
```

на:

```jsx
{can.publish && config.supportsImport ? (
  <button type="button" className="ntv2-btn" ...>
    Импортировать библиотеку
  </button>
) : null}
```

Дополнительно можно скрывать кнопку, если:

```js
config.importEndpoint === false
```

или если backend capabilities API говорит, что import не поддержан.

## 1.4. Backend-вариант

Если импорт для конкретного конструктора действительно нужен, тогда нужно не только показать кнопку, но и добавить backend route:

```text
POST /api/admin/v2/<base>/import
```

При этом route должен:

- требовать правильное publish/import permission;
- поддерживать dry-run, если используется;
- возвращать понятный report;
- не создавать дубли;
- не затирать manual edits без подтверждения.

## 1.5. Критерии готовности

Готово, если:

- кнопка **Импортировать библиотеку** скрыта для конструкторов без import route;
- кнопка отображается только при `can.publish && supportsImport`;
- конструкторы formulas/professions/workshops/PVP/combat/NPC allies не вызывают 404/405 при отсутствии import route;
- если импорт нужен — backend route добавлен;
- UI не показывает нерабочие действия;
- есть тест или checklist для секций с import и без import.

---

# 2. GlobalSearch должен быть доступен только при `graph.view` или не должен разлогинивать

## 2.1. Проблема

В `web/src/components/admin-shell/AdminShell.jsx` глобальный поиск:

```jsx
<GlobalSearch guarded={guarded} onOpen={setActive} />
```

рендерится для каждого залогиненного администратора.

Но endpoint:

```text
/api/admin/v2/search
```

требует:

```text
graph.view
```

Default роли вроде:

- moderator;
- support;
- read-only;

могут не иметь `graph.view`.

Сценарий:

1. Админ без `graph.view` вводит 2 символа.
2. Frontend вызывает `/api/admin/v2/search`.
3. Backend возвращает `403`.
4. `requestAdminJson` воспринимает это как проблему с сессией.
5. Admin session token очищается.
6. Админ вылетает из панели из-за harmless search.

## 2.2. Требование

Нужно исправить оба уровня.

### Уровень A — UI gate

Не показывать или отключать GlobalSearch без `graph.view`.

```jsx
{hasPerm("graph.view") ? (
  <GlobalSearch guarded={guarded} onOpen={setActive} />
) : null}
```

Если в UI есть объект permissions:

```js
canGraphView
```

использовать его.

### Уровень B — не разлогинивать на обычный `403`

`requestAdminJson` не должен очищать session token при каждом `403`.

Различать:

- `401 Unauthorized` — сессия недействительна, можно очищать token;
- `403 Forbidden` — прав недостаточно, token валиден, не разлогинивать.

## 2.3. Альтернативный вариант

Можно сделать `/api/admin/v2/search` доступным любому авторизованному админу, но результаты фильтровать по правам.

Тогда:

- support видит только игроков/разрешённые секции;
- moderator видит только разрешённые инструменты;
- graph/world/admin-only объекты скрыты.

Минимально нужно сделать UI gate + не очищать token на `403`.

## 2.4. Критерии готовности

Готово, если:

- GlobalSearch скрыт или disabled без `graph.view`;
- ввод в поиск не разлогинивает админа без `graph.view`;
- `403` больше не очищает admin session token;
- `401` по-прежнему обрабатывается как истёкшая/недействительная сессия;
- ошибка прав показывается понятно;
- есть тест/checklist для роли moderator/support без `graph.view`.

---

# 3. Скрыть «Открыть профиль» игрока без edit permission

## 3.1. Проблема

Endpoint:

```text
player_view_token
```

был усилен и теперь требует не просто:

```text
players.view
```

а edit-право, потому что токен открывает редактируемый профиль игрока.

В коде указано, что такой токен даёт доступ к действиям вроде:

- выброс предметов;
- смена имени;
- очки;
- курьер;
- другие редактируемые действия.

Но player card в UI всё ещё показывает кнопку:

```text
Открыть профиль
```

каждому пользователю с `players.view`.

Сценарий:

1. Support/moderator/read-only открывает карточку игрока.
2. Видит кнопку **Открыть профиль**.
3. Нажимает.
4. Backend возвращает `403`.
5. `requestAdminJson` очищает session token.
6. Админ разлогинен.

## 3.2. Требование

Кнопка **Открыть профиль** должна показываться только если у администратора есть право, которое реально требуется endpoint.

Сейчас endpoint требует:

```text
PERM_INVENTORY_EDIT
```

Значит UI должен проверять соответствующее permission.

## 3.3. Важное уточнение по смыслу кнопки

Нужно разделить два действия.

### Действие A — Просмотреть профиль read-only

Для `players.view` можно сделать отдельную кнопку:

```text
Просмотреть профиль
```

Она должна открывать профиль в read-only режиме без прав редактирования.

### Действие B — Открыть редактируемый профиль

Для `inventory.edit` или другого edit-права:

```text
Открыть редактируемый профиль
```

Этот токен может давать действия изменения, поэтому должен быть доступен только тем, кто имеет нужное edit-право.

## 3.4. Требование к безопасности

Read-only token не должен позволять:

- выбрасывать предметы;
- менять имя;
- распределять очки;
- использовать курьера;
- надевать/снимать вещи;
- изменять инвентарь;
- выполнять игровые действия от имени игрока.

Editable token должен требовать edit permission.

## 3.5. Критерии готовности

Готово, если:

- кнопка editable profile скрыта без `inventory.edit` или нужного edit-права;
- `players.view` пользователь не получает edit-token;
- support/moderator/read-only не разлогинивается при просмотре player card;
- если нужен read-only просмотр профиля — он реализован отдельным безопасным endpoint/token;
- `403` не очищает session token;
- есть тест/checklist для роли с `players.view`, но без `inventory.edit`.

---

# 4. Скрыть rollback для published items без publish rights

## 4.1. Проблема

В `LibrarySection.jsx` для истории версий используется:

```jsx
<VersionHistory
  base={base}
  id={editing.id}
  canRollback={can.edit}
  onRolledBack={refreshEditing}
/>
```

Но rollback endpoint для опубликованных записей теперь требует matching `*.publish` permission дополнительно к edit.

Итог:

- content-role editor с `*.edit`, но без `*.publish`, видит кнопку **Откатить**;
- нажимает rollback published item;
- получает `403`;
- `requestAdminJson` может очистить session token;
- админ разлогинен.

## 4.2. Требование

Rollback control должен учитывать статус записи.

Правило:

```text
draft/не published: rollback можно показывать при can.edit
published: rollback можно показывать только при can.edit && can.publish
```

## 4.3. Правильная логика frontend

В `LibrarySection.jsx`:

```jsx
const canRollback =
  can.edit && (editing.status !== "published" || can.publish);
```

И передать:

```jsx
<VersionHistory
  base={base}
  id={editing.id}
  canRollback={canRollback}
  onRolledBack={refreshEditing}
/>
```

Если статус находится не в `editing.status`, брать из envelope/status текущей записи.

## 4.4. Backend тоже должен оставаться строгим

Frontend gate нужен для UX, но backend всё равно должен проверять права.

Rollback endpoint должен:

- требовать edit для draft;
- требовать edit + publish для published;
- возвращать понятную `403`, если прав недостаточно;
- не считать `403` истёкшей сессией.

## 4.5. Критерии готовности

Готово, если:

- rollback draft item виден при `can.edit`;
- rollback published item виден только при `can.edit && can.publish`;
- editor без publish не видит rollback для published;
- backend сохраняет проверку прав;
- `403` не очищает session token;
- есть тест/checklist для published constructor item без publish-права.

---

# 5. Общая правка `requestAdminJson`: не очищать session на обычный 403

## 5.1. Проблема

Во всех описанных случаях есть общий симптом:

```text
обычный отказ в правах приводит к очистке admin session token
```

Это плохой UX и опасное поведение.

`403 Forbidden` означает:

```text
пользователь авторизован, но ему не хватает прав
```

Это не то же самое, что истёкшая сессия.

## 5.2. Требование

Изменить обработку ошибок:

- `401` — можно считать сессию истёкшей/недействительной;
- `403` — показать ошибку прав, но не очищать token;
- `404/405` — показать техническую ошибку route/action not supported, не очищать token;
- network error — показать ошибку сети, не очищать token;
- `5xx` — показать ошибку сервера, не очищать token.

## 5.3. Сообщения на русском

Примеры:

```text
Недостаточно прав для выполнения действия.
```

```text
Действие недоступно для этого раздела.
```

```text
Маршрут импорта для этого конструктора не подключён.
```

```text
Сессия истекла. Войдите заново.
```

Последнее использовать только для `401`.

## 5.4. Критерии готовности

Готово, если:

- `403` не разлогинивает администратора;
- `404/405` не разлогинивают администратора;
- `401` корректно завершает сессию;
- пользователь видит понятное сообщение;
- все действия выше больше не вызывают внезапный logout.

---

# 6. Backend capabilities для секций админки

## 6.1. Проблема

Frontend часто предполагает наличие backend route на основе generic config и permissions.

Это приводит к кнопкам, которые UI показывает, но backend не поддерживает.

## 6.2. Требование

Добавить или расширить механизм capabilities.

Для каждой секции/конструктора backend или frontend config должен явно знать:

- поддерживает ли create;
- поддерживает ли edit;
- поддерживает ли publish;
- поддерживает ли disable;
- поддерживает ли archive;
- поддерживает ли delete;
- поддерживает ли import;
- поддерживает ли validate;
- поддерживает ли rollback;
- поддерживает ли graph relations;
- какие permissions нужны для каждого действия.

## 6.3. Минимальная реализация

Минимально добавить в frontend config:

```js
supportsImport: false
supportsRollback: true
supportsValidate: true
```

И использовать эти флаги вместе с permissions.

Лучше — получать capabilities от backend.

## 6.4. Критерии готовности

Готово, если:

- UI не показывает действия без route/capability;
- каждая секция знает, какие действия поддерживает;
- generic LibrarySection больше не делает ложных предположений;
- при добавлении нового конструктора нужно явно указать capabilities.

---

# 7. Общие тесты и checklist

Нужно проверить роли:

- superadmin;
- admin;
- content editor;
- economy editor;
- support;
- moderator;
- read-only.

## Import button

- секция с import route показывает кнопку при publish + supportsImport;
- секция без import route не показывает кнопку;
- нет 404/405 при работе UI.

## Global search

- роль с graph.view видит поиск;
- роль без graph.view не видит поиск или видит disabled;
- ввод в поиск не разлогинивает.

## Player profile

- роль с players.view, но без inventory.edit не видит edit-profile action;
- роль с inventory.edit видит action;
- read-only профиль, если реализован, не даёт edit-действий.

## Rollback

- draft item rollback доступен editor;
- published item rollback доступен только при publish;
- editor без publish не видит rollback published item.

## Error handling

- 401 очищает session;
- 403 не очищает session;
- 404/405 не очищают session;
- сообщения понятны.

---

# 8. Общие критерии готовности

Задача считается выполненной, если:

- кнопка **Импортировать библиотеку** скрыта для секций без import route;
- GlobalSearch gated по `graph.view` или endpoint безопасно доступен всем авторизованным с фильтрацией;
- кнопка **Открыть профиль** не показывается пользователям без edit permission;
- rollback published items скрыт без publish permission;
- `requestAdminJson` не очищает token на `403`;
- `requestAdminJson` не очищает token на `404/405`;
- `401` по-прежнему завершает сессию;
- UI действия синхронизированы с backend capabilities;
- все ошибки и подсказки на русском;
- добавлены тесты/checklist для разных ролей.
