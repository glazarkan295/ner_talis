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
