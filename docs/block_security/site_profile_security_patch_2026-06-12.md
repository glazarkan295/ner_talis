# Патч безопасности сайта профиля — 2026-06-12

## Что исправлено

1. **Одноразовый URL-токен профиля**
   - Ссылка из бота теперь создаёт `activation`-токен.
   - При первом обращении к `/api/profile/{token}` сервер удаляет URL-токен и выдаёт отдельный активный `sessionToken`.
   - Повторное открытие старой ссылки с тем же URL-токеном возвращает `401`.

2. **Новый токен отключает старую активную сессию**
   - При создании новой ссылки профиля удаляются все старые activation/active сессии этого игрока для того же scope.
   - Если игрок открыл новую ссылку из бота, прежняя вкладка/старый session-token больше не проходят API-проверку.

3. **Токен больше не хранится в localStorage**
   - Фронтенд удаляет старый `ner_talis_profile_token` из `localStorage`.
   - Новый активный токен хранится только в `sessionStorage`.
   - URL очищается через `history.replaceState(...)`: `token` и `t` убираются из адресной строки после чтения.

4. **Закрыта утечка полного профиля через public_id**
   - `/api/profile/{identifier}` больше не отдаёт полный React JSON по `public_id`.
   - Полный профиль доступен только по bot-link/session-token.
   - Legacy `/api/player/profile/{identifier}` также требует приватную сессию.
   - Публичная серверная карточка сокращена: не отдаёт деньги, инвентарь, экипировку, характеристики и привязанные платформы.

5. **Защита от спама API**
   - Добавлен middleware rate-limit для `/api/profile...` и `/api/player/profile...`.
   - Настройки через env:
     - `PROFILE_POST_RATE_LIMIT` — лимит POST за окно, по умолчанию `40`.
     - `PROFILE_GET_RATE_LIMIT` — лимит GET за окно, по умолчанию `120`.
     - `RATE_LIMIT_WINDOW_SECONDS` — окно в секундах, по умолчанию `60`.
   - При превышении лимита возвращается `429`.

6. **Security headers**
   - Добавлены `Content-Security-Policy`, `Strict-Transport-Security`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`.
   - Для `/profile`, `/pavilion` и `/api/*` добавлен `Cache-Control: no-store`.
   - Добавлен `TrustedHostMiddleware`.
   - Разрешённые host настраиваются через `ALLOWED_HOSTS`.

## Изменённые файлы

- `ner_talis_game_project/storage/hard_delete_runtime.py`
- `ner_talis_game_project/storage/postgres_storage.py`
- `ner_talis_game_project/site_api.py`
- `ner_talis_game_project/web_app.py`
- `web/src/api/profileApi.js`
- `ner_talis_game_project/tests/test_profile_site_fixes.py`

## Проверки

- Полный pytest из корня проекта: `314 passed, 1 skipped, 249 subtests passed`.
- Python compile all: OK.
- `web/src/api/profileApi.js`: `node -c` OK.
- Security headers вручную проверены через `TestClient /health`.
- Rate-limit вручную проверен: третий запрос при лимите 2 возвращает `429`.

## Замечание по frontend build

`npm run build` не запускался до конца в контейнере, потому что в архиве нет `web/node_modules`, а команда завершилась `vite: not found`. JS-файл профиля проверен синтаксически через `node -c`; для production-сборки нужно выполнить `npm install`/`npm ci` в окружении с доступом к npm-пакетам.
