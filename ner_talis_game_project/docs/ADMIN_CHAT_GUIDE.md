# Административный чат Нер-Талис

Админ-чат нужен, чтобы через Telegram или VK управлять служебными действиями без прямого доступа к базе.

## Что умеет

- добавлять один промокод;
- массово загружать промокоды JSON-массивом;
- отключать промокод;
- смотреть последние промокоды;
- искать игрока по `game_id`, имени, `public_id`, Telegram/VK id;
- смотреть короткую админ-карточку игрока;
- добавлять или списывать медные монеты с обязательным подтверждением;
- начислять крупицы опыта, очки характеристик и очки навыков по правилу 1 единица = 1 очко/опыт;
- отключать активные web-сессии профиля игрока;
- обнулять прогресс игрока по `game_id`;
- полностью удалять профиль игрока по игровому ID и возвращать его на регистрацию;
- добавлять предмет игроку;
- добавлять предмет с полными JSON-полями;
- писать audit log;
- делать backup профиля игрока перед сбросом, добавлением предметов и изменением монет.

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

Промокод на опыт:

```text
/admin_promo_add EXP4500 100 {"experience":4500}
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


### Найти игрока

```text
/admin_find_player QUERY
```

Ищет по `game_id`, имени, `public_id`, Telegram/VK id и привязкам вида `telegram:123` / `vk:123`.

Пример:

```text
/admin_find_player NT-1A2B3C4D5E
/admin_find_player НикИгрока
/admin_find_player telegram:123456789
```

### Карточка игрока для админа

```text
/admin_player_info GAME_ID
```

Показывает короткую сводку: имя, `game_id`, `public_id`, привязки, уровень, опыт, монеты, HP, энергию, текущую локацию, бой/смерть, количество стеков инвентаря, занятые слоты экипировки и активные эффекты. Команда не отдаёт полный сырой JSON в чат.

### Добавить или списать медные монеты

```text
/admin_add_money GAME_ID AMOUNT CONFIRM
```

`AMOUNT` может быть положительным или отрицательным. Списание не может увести монеты игрока ниже нуля. Перед успешным изменением создаётся backup профиля, действие пишется в audit log.

Пример:

```text
/admin_add_money NT-1A2B3C4D5E 1000 CONFIRM
/admin_add_money NT-1A2B3C4D5E -500 CONFIRM
```


### Начислить крупицы опыта

```text
/admin_add_experience GAME_ID AMOUNT CONFIRM
```

Алиас:

```text
/admin_add_exp GAME_ID AMOUNT CONFIRM
```

`AMOUNT` — положительное целое число. Правило ресурса: 1 крупица опыта = 1 единица опыта. Команда начисляет опыт ровно 1 к 1, обрабатывает повышение уровня и выдаёт свободные очки за уровень.

Пример:

```text
/admin_add_experience NT-1A2B3C4D5E 4500 CONFIRM
```

### Добавить или списать очки характеристик

```text
/admin_add_stat_points GAME_ID AMOUNT CONFIRM
```

Алиас:

```text
/admin_add_attribute_points GAME_ID AMOUNT CONFIRM
```

`AMOUNT` может быть положительным или отрицательным. Списание не может увести свободные очки характеристик ниже нуля. Правило ресурса: 1 очко характеристик = 1 свободное очко характеристик.

Пример:

```text
/admin_add_stat_points NT-1A2B3C4D5E 5 CONFIRM
/admin_add_stat_points NT-1A2B3C4D5E -2 CONFIRM
```

### Добавить или списать очки навыков

```text
/admin_add_skill_points GAME_ID AMOUNT CONFIRM
```

`AMOUNT` может быть положительным или отрицательным. Списание не может увести свободные очки навыков ниже нуля. Правило ресурса: 1 очко навыка = 1 свободное очко навыка.

Пример:

```text
/admin_add_skill_points NT-1A2B3C4D5E 10 CONFIRM
/admin_add_skill_points NT-1A2B3C4D5E -3 CONFIRM
```

### Отключить активные web-сессии профиля

```text
/admin_kick_profile_sessions GAME_ID CONFIRM
```

Удаляет активные сессии сайта профиля для игрока. Полезно после подозрительного входа, пересланной ссылки или смены правил безопасности.

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

Перед сбросом, добавлением предметов и изменением монет создаётся backup профиля в `ADMIN_BACKUP_DIR`.
Полное удаление игрока backup не создаёт и удаляет профиль безоговорочно.
Все действия пишутся в `ADMIN_AUDIT_LOG_PATH`.
