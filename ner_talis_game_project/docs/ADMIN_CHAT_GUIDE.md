# Административный чат Нер-Талис

Админ-чат нужен, чтобы через Telegram или VK управлять служебными действиями без прямого доступа к базе.

## Что умеет

- добавлять один промокод;
- массово загружать промокоды JSON-массивом;
- отключать промокод;
- смотреть последние промокоды;
- обнулять прогресс игрока по `game_id`;
- полностью удалять профиль игрока по игровому ID и возвращать его на регистрацию;
- добавлять предмет игроку;
- добавлять предмет с полными JSON-полями;
- писать audit log;
- делать backup профиля игрока перед сбросом и добавлением предметов.

## Переменные окружения

Минимально для доступа достаточно указать ID админов:

```env
TELEGRAM_ADMIN_USER_IDS=111111111,222222222
VK_ADMIN_USER_IDS=111111111,222222222
```

Дополнительно можно ограничить команды конкретным Telegram-чатом или VK-беседой:

```env
TELEGRAM_ADMIN_CHAT_IDS=-1001234567890
VK_ADMIN_PEER_IDS=2000000001
```

Служебные пути:

```env
PROMO_CODES_PATH=data/promo_codes.json
ADMIN_AUDIT_LOG_PATH=data/admin_audit.log
ADMIN_BACKUP_DIR=data/admin_backups
```

Значения `chat_id`, `peer_id` и `user_id` можно узнать командой:

```text
/admin_id
```

## Команды

### Справка

```text
/admin_help
```

### Добавить промокод

```text
/admin_promo_add CODE USES REWARD_JSON
```

Пример:

```text
/admin_promo_add START100 100 {"money":1000,"items":[{"item_id":"small_potion","amount":3}]}
```

### Массовая загрузка промокодов

```text
/admin_promo_bulk JSON_ARRAY
```

Пример:

```text
/admin_promo_bulk [{"code":"A1","uses_left":10,"reward":{"money":500}}]
```

### Отключить промокод

```text
/admin_promo_off CODE
```

### Список промокодов

```text
/admin_promo_list
```

### Обнулить прогресс игрока

```text
/admin_reset_player GAME_ID CONFIRM
```

`CONFIRM` обязателен, чтобы случайно не стереть прогресс игрока.
Сброс делает backup старого состояния и возвращает игроку стартовые предметы/навыки.

### Полностью удалить профиль игрока

```text
/admin_delete_player NT-XXXXXXXXXX CONFIRM_DELETE
```

`CONFIRM_DELETE` обязателен, чтобы случайно не удалить профиль.
Удаление работает только по игровому ID вида `NT-XXXXXXXXXX`.

Пример:

```text
/admin_delete_player NT-1A2B3C4D5E CONFIRM_DELETE
```

После удаления очищаются:

- профиль игрока;
- Telegram/VK-привязки;
- занятое имя;
- коды привязки;
- web/site-сессии.

Удаление профиля выполняется без backup старого персонажа. После этого игрок при любой следующей команде будет отправлен на начало регистрации и начнёт полностью с нуля.

### Добавить простой предмет

```text
/admin_add_item GAME_ID ITEM_ID AMOUNT QUALITY
```

Пример:

```text
/admin_add_item NT-000001 iron_sword 1 редкий
```

### Добавить предмет JSON-объектом

```text
/admin_add_item_json GAME_ID ITEM_JSON
```

Пример:

```text
/admin_add_item_json NT-000001 {"item_id":"ring_test","name":"Тестовое кольцо","amount":1,"quality":"эпический"}
```

## Безопасность

Команды выполняются только если user id администратора находится в списке `TELEGRAM_ADMIN_USER_IDS` или `VK_ADMIN_USER_IDS`.
Если заданы `TELEGRAM_ADMIN_CHAT_IDS` или `VK_ADMIN_PEER_IDS`, команда дополнительно должна прийти из разрешённого чата/беседы.

Перед сбросом и добавлением предметов создаётся backup профиля в `ADMIN_BACKUP_DIR`.
Полное удаление игрока backup не создаёт и удаляет профиль безоговорочно.
Все действия пишутся в `ADMIN_AUDIT_LOG_PATH`.
