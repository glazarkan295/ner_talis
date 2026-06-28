# Обновление для Timeweb App Platform Dockerfile

Файлы Timeweb/Docker лежат в корне репозитория. Сам код ботов находится в `ner_talis_game_project/`, а игровые JSON-данные — в `data/`.

Итоговая структура должна быть такой:

```text
ner_talis/
├─ Dockerfile
├─ .dockerignore
├─ .gitignore
├─ .env.example
├─ timeweb_start.py
├─ data/
├─ web/
└─ ner_talis_game_project/
   ├─ requirements.txt
   ├─ main.py
   ├─ main_telegram.py        # внутренний модуль Telegram-приложения
   ├─ web_app.py              # FastAPI-сайт, /health и /ready
   ├─ site_api.py             # API профиля для React-сайта
   ├─ handlers/
   ├─ services/
   ├─ storage/
   ├─ keyboards/
   └─ texts/
```

## Что делает обновление

- `Dockerfile` собирает React-профиль и Python 3.12 контейнер.
- `Dockerfile` содержит `HEALTHCHECK`, который проверяет `/health` через Python без `curl`.
- `timeweb_start.py` запускает FastAPI-сайт на `PORT=8080`, затем поднимает Telegram и VK ботов.
- `/health` всегда проверяет, что контейнер жив и слушает порт. Он не зависит от PostgreSQL/SQLite и должен отвечать даже при ошибке базы.
- `/ready` проверяет доступность хранилища игроков и вернёт `503`, если PostgreSQL/SQLite недоступен или неправильно настроен.
- Если хранилище или боты временно не готовы, контейнер не падает сразу: фоновые сервисы повторяют запуск через `APP_RESTART_RETRY_SECONDS`.
- `.dockerignore` не отправляет в Docker лишние файлы, `.env`, кэш Python и локальную базу игроков.
- `.env.example` хранит шаблон переменных без реальных токенов.

## Важно

Настоящий `.env` не загружай в GitHub.
Токены Telegram/VK вставляй в панели Timeweb в переменные окружения.
В панели Timeweb имя и значение вводятся отдельно: в поле имени `TELEGRAM_BOT_TOKEN`, в поле значения только сам токен без `TELEGRAM_BOT_TOKEN=`.

Минимальные переменные:

```env
TELEGRAM_BOT_TOKEN=...
VK_GROUP_TOKEN=...
VK_GROUP_ID=...
APP_ENV=production
LOG_LEVEL=INFO
PORT=8080
APP_PORT=8080
APP_RESTART_RETRY_SECONDS=30
STORAGE_BACKEND=postgres
DATABASE_URL=postgresql://user:password@host:5432/db_name
PLAYERS_STORAGE_PATH=data/players.json
SITE_BASE_URL=https://your-domain.ru
SITE_PROFILE_BASE_URL=https://your-domain.ru/profile
SITE_PAVILION_URL=https://your-domain.ru/pavilion
```

### Production-переменные безопасности и хранилища

Эти переменные есть в `.env.timeweb.postgresql.example` и важны для боевого запуска (без них сайт работает, но менее защищён/корректен):

```env
# Хранилище: запретить тихий откат на JSON в проде (требуем Postgres)
ALLOW_JSON_STORAGE_IN_PRODUCTION=false
# Защита хостов и заголовки/HTTPS
ALLOWED_HOSTS=ner-talis-game.ru,www.ner-talis-game.ru,localhost,127.0.0.1
ENABLE_HSTS=true
FORCE_HTTPS=true
# За reverse proxy Timeweb нужно доверять proxy-заголовкам HTTPS (иначе ошибка
# {"detail":"HTTPS required"} при открытии профиля/админки):
UVICORN_PROXY_HEADERS=true
UVICORN_FORWARDED_ALLOW_IPS=*
TRUST_PROXY_HEADERS=true
TRUSTED_PROXY_IPS=*
# Постоянный диск под загрузки админки (иконки переживают пересборку контейнера)
PUBLIC_UPLOADS_ASSETS_DIR=data/public_uploads/assets
# OpenAPI/Swagger по умолчанию ВЫКЛЮЧЕНЫ в проде (раскрывают список ручек/схемы).
# Включать только для разработки.
ENABLE_API_DOCS=false
```

Если за Timeweb стоит балансировщик/прокси с фиксированным IP — вместо `TRUSTED_PROXY_IPS=*` безопаснее перечислить его IP или CIDR-сети (например `10.0.0.0/8,172.16.0.0/12,192.168.0.0/16`), иначе любому отправителю можно будет доверять proxy-заголовки.

### Ошибка `{"detail":"HTTPS required"}`

Если при открытии `/profile?token=...` или `/admin_panel_v2?token=...` сайт возвращает JSON `{"detail":"HTTPS required","redirect":"https://..."}` — приложение за reverse proxy Timeweb видит запрос как HTTP (TLS терминируется на прокси, до Uvicorn доходит HTTP), а `FORCE_HTTPS=true` блокирует «небезопасный» доступ.

Решение — включить доверие proxy-заголовкам HTTPS:

```env
FORCE_HTTPS=true
UVICORN_PROXY_HEADERS=true
UVICORN_FORWARDED_ALLOW_IPS=*
TRUST_PROXY_HEADERS=true
TRUSTED_PROXY_IPS=*
```

Как это работает:

- `UVICORN_PROXY_HEADERS=true` + `UVICORN_FORWARDED_ALLOW_IPS=*` — Uvicorn доверяет `X-Forwarded-Proto`/`X-Forwarded-For` от прокси и переписывает scheme на `https`;
- `TRUST_PROXY_HEADERS=true` + `TRUSTED_PROXY_IPS` — приложение дополнительно признаёт запрос защищённым по `X-Forwarded-Proto: https`, `X-Forwarded-Ssl: on` или `Forwarded: proto=https`, если ближайший узел доверенный;
- прямой HTTP без доверенного proxy по-прежнему блокируется.

Аварийный временный обход (если HTTPS уже обеспечивает внешний proxy, а правка ещё не применена): `FORCE_HTTPS=false`. Снимите его после настройки proxy-заголовков.

После такой ошибки **перевыпустите ссылки профиля/админки через бота** — токены могли попасть в логи/сообщения. Не публикуйте реальные токены в чатах и на скриншотах.

Раздельных режимов запуска больше нет: `main.py` всегда запускает Telegram и VK вместе, поэтому нужны все три переменные `TELEGRAM_BOT_TOKEN`, `VK_GROUP_TOKEN`, `VK_GROUP_ID`.

Если Timeweb нестабильно достучаться до Telegram API, можно оставить стандартные значения таймаутов из `.env.example`: `TELEGRAM_GET_UPDATES_READ_TIMEOUT=60`, `TELEGRAM_POLL_TIMEOUT=30`, `TELEGRAM_BOOTSTRAP_RETRIES=-1`.

Если старый контейнер или локальный запуск ещё использует тот же Telegram token, оставь `TELEGRAM_RETRY_ON_CONFLICT=true`. Новый контейнер будет держать сайт живым и повторять polling.

Если токен попал в логи, перевыпусти его через BotFather и обнови переменную окружения в Timeweb.

Для Timeweb рекомендуется `STORAGE_BACKEND=postgres`. SQLite подходит только для локальных тестов или постоянного диска. Старый `data/players.json` автоматически переносится при первом запуске.

Важно: если App Platform пересоздаёт контейнер без постоянного диска, локальный SQLite-файл тоже может потеряться. Для долгого продакшена лучше указать `SQLITE_STORAGE_PATH` на постоянный том или вынести игроков в управляемую БД.

## Локальная проверка Docker

```bash
docker build -t ner-talis-bot .
docker run --rm -p 8080:8080 --env-file .env ner-talis-bot
```

Проверка health и ready endpoint:

```bash
curl http://localhost:8080/health
curl http://localhost:8080/ready
```

`/health` должен вернуть:

```text
OK
```

`/ready` должен вернуть:

```json
{"status":"ready"}
```

Если `/ready` возвращает `503`, контейнер жив, но нужно проверить `DATABASE_URL`, `STORAGE_BACKEND` и логи.

## Важно по DATABASE_URL

В переменную `DATABASE_URL` в Timeweb вставляйте только значение, без `DATABASE_URL=` и без кавычек.

Правильно:

```env
postgresql://user:password@host:5432/db_name
```

Неправильно:

```env
DATABASE_URL=postgresql://user:password@host:5432/db_name
'postgresql://user:password@host:5432/db_name'
postgresql://user:password@host:5432/default_db'
```

Если в логах есть `database "default_db'" does not exist`, значит в конце имени базы попала лишняя кавычка или указано неверное имя базы.

## Исправление чёрного экрана / unhealthy

В этой версии исправлена ошибка запуска FastAPI, из-за которой контейнер мог уходить в `unhealthy`: у маршрута `/` убрана проблемная аннотация `HTMLResponse | FileResponse`, а маршруты сайта помечены `response_model=None`.

Проверки после деплоя:

```text
https://ner-talis-game.ru/health
```

Должно вернуть:

```text
OK
```

```text
https://ner-talis-game.ru/ready
```

Должно вернуть `{"status":"ready"}`. Если там `storage_error`, сайт живой, но проблема в `DATABASE_URL` или `STORAGE_BACKEND`.

Если открывается просто чёрный экран:

1. Открой `/health`. Если нет `OK`, значит FastAPI не поднялся.
2. Открой `/ready`. Если `storage_error`, исправь `DATABASE_URL`.
3. Открой новую ссылку через кнопку бота «Профиль на сайте» — старые ссылки могут истечь.
4. Убедись, что в Timeweb нет второго контейнера/приложения с тем же Telegram token, иначе будет `Conflict: terminated by other getUpdates request`.

Для Timeweb оставь порт:

```env
APP_HOST=0.0.0.0
APP_PORT=8080
PORT=8080
```


## Добавленные ассеты предметов и PVE-бой

В проект встроены реалистичные PNG-иконки предметов для «Холмистых лугов». Они лежат в `web/public/assets/items/hilly_meadows/` и отдаются сайтом по путям вида `/assets/items/hilly_meadows/...`.

Также подключён первый рабочий PVE-модуль. Случайное событие «Битва» в «Холмистых лугах» теперь создаёт активный бой, блокирует городские переходы до завершения боя и использует кнопки боя в Telegram/VK.
