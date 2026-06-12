# Блок админ-чата и админ-команд v2

Источник: `ner_talis-main-51-site-security-patched.zip`.

## Что добавлено

- `/admin_find_player QUERY` — поиск игрока по `game_id`, имени, `public_id`, Telegram/VK id и привязкам вида `telegram:123` / `vk:123`.
- `/admin_player_info GAME_ID` — короткая админ-карточка игрока без вывода полного сырого JSON в чат.
- `/admin_add_money GAME_ID AMOUNT CONFIRM` — добавление или списание медных монет с обязательным подтверждением, backup и audit log.
- `/admin_kick_profile_sessions GAME_ID CONFIRM` — отключение активных web/site-сессий профиля игрока.
- `ADMIN_COMMANDS_REQUIRE_CHAT` — опциональный строгий режим: если включён, команды требуют настроенный разрешённый Telegram-чат/VK-беседу.

## Безопасность

- Все опасные действия требуют явного `CONFIRM` или `CONFIRM_DELETE`.
- Изменение монет и добавление предметов делают backup профиля.
- Списание монет не может увести баланс ниже нуля.
- Слишком большие суммы изменения монет отклоняются.
- Действия `add_money` и `kick_profile_sessions` пишутся в `ADMIN_AUDIT_LOG_PATH`.
- Поиск и карточка игрока возвращают короткий текст, а не полный JSON-профиль.
- Доступ остаётся через `TELEGRAM_ADMIN_USER_IDS` / `VK_ADMIN_USER_IDS`; при заданных `TELEGRAM_ADMIN_CHAT_IDS` / `VK_ADMIN_PEER_IDS` команды дополнительно ограничены разрешённым чатом/беседой.

## Изменённые файлы

- `.env.example`
- `ner_talis_game_project/services/admin_access.py`
- `ner_talis_game_project/services/admin_command_service.py`
- `ner_talis_game_project/services/admin_player_service.py`
- `ner_talis_game_project/handlers/telegram_admin.py`
- `ner_talis_game_project/docs/ADMIN_CHAT_GUIDE.md`
- `ner_talis_game_project/tests/test_admin_chat_commands_v2.py`

## Проверка

Полный запуск из корня проекта:

```text
319 passed, 1 skipped, 251 subtests passed
```

Дополнительно:

- `compileall ner_talis_game_project` — OK.
- JSON-файлов проверено: 47.
- Ошибок чтения JSON: 0.
- Asset-ссылок проверено: 199.
- Битых asset-ссылок: 0.
