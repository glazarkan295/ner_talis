# Административный чат Нер-Талис

Админ-чат нужен, чтобы через Telegram или VK управлять служебными действиями без прямого доступа к базе.

## Что умеет

- добавлять один промокод;
- массово загружать промокоды JSON-массивом;
- отключать промокод;
- смотреть последние промокоды;
- обнулять прогресс игрока по `game_id`;
- удалять профиль игрока и возвращать его на регистрацию;
- добавлять предмет игроку;
- добавлять предмет с полными JSON-полями;
- писать audit log;
- делать backup профиля игрока перед опасными действиями.

## Переменные окружения

Добавить в Timeweb Cloud:

```env
TELEGRAM_ADMIN_CHAT_IDS=-1001234567890
TELEGRAM_ADMIN_USER_IDS=111111111,222222222
VK_ADMIN_PEER_IDS=2000000001
VK_ADMIN_USER_IDS=111111111,222222222
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

### Удалить профиль игрока

```text
/admin_delete_player ID CONFIRM_DELETE
```

`CONFIRM_DELETE` обязателен, чтобы случайно не удалить профиль.
После удаления игрок при следующем `/start` снова попадает на регистрацию персонажа.

Поддерживаемые варианты `ID`:

```text
/admin_delete_player NT-ABC1234567 CONFIRM_DELETE
/admin_delete_player tg_123456 CONFIRM_DELETE
/admin_delete_player telegram:123456 CONFIRM_DELETE
/admin_delete_player vk_123456 CONFIRM_DELETE
/admin_delete_player vk:123456 CONFIRM_DELETE
/admin_delete_player PUBLIC_ID CONFIRM_DELETE
```

В Telegram-группе команда также работает в виде `/admin_delete_player@BotName ...`.

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

Команды выполняются только если одновременно совпали:

- разрешённый чат или беседа;
- разрешённый user id администратора.

Перед сбросом, удалением игрока и добавлением предметов создаётся backup профиля в `ADMIN_BACKUP_DIR`.
Все действия пишутся в `ADMIN_AUDIT_LOG_PATH`.
