# Timeweb App Platform — Нер-Талис

Проект запускается одной командой через Dockerfile:

```bash
python timeweb_start.py
```

`timeweb_start.py` поднимает сразу три части:

1. FastAPI-сайт на `APP_HOST:APP_PORT`.
2. VK-бот в отдельном потоке.
3. Telegram-бот через общий `main.py`.

Раздельных режимов запуска нет.

## Что нужно создать в Timeweb

1. App Platform приложение из репозитория с Dockerfile.
2. Управляемую базу PostgreSQL.
3. Домен для сайта.
4. Переменные окружения в настройках приложения.

## Минимальные переменные окружения

```env
TELEGRAM_BOT_TOKEN=...
VK_GROUP_TOKEN=...
VK_GROUP_ID=...

STORAGE_BACKEND=postgres
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB_NAME

SITE_BASE_URL=https://your-domain.ru
WEB_SESSION_SECRET=long_random_secret
WEB_SESSION_TTL_MINUTES=15

APP_HOST=0.0.0.0
APP_PORT=8080
PORT=8080
LOG_LEVEL=INFO
LOG_FILE_PATH=logs/ner_talis.log
```

В Timeweb имя и значение переменной вводятся отдельно. В значение токена не вставляй `TELEGRAM_BOT_TOKEN=` — только сам токен.

## Важные URL

```text
/health
/profile?token=...
/profile/<token>              # поддерживается для уже созданных старых ссылок
/api/player/profile?token=...
/api/player/profile/<token>   # поддерживается для старых ссылок/API
/pavilion?token=...
/pavilion/<token>             # поддерживается для старых ссылок
```

Кнопка в боте **«Профиль на сайте»** создаёт токен в `web_sessions` и отправляет ссылку:

```text
https://your-domain.ru/profile?token=...
```

Старый вариант тоже будет работать:

```text
https://your-domain.ru/profile/<token>
```

## PostgreSQL

При первом запуске автоматически создаются таблицы:

- `players` — профили игроков;
- `platform_links` — связка Telegram/VK с единым `game_id`;
- `link_codes` — временные коды привязки платформ;
- `web_sessions` — временные токены входа на сайт.

Для локальной разработки можно временно использовать SQLite:

```env
STORAGE_BACKEND=sqlite
SQLITE_STORAGE_PATH=data/players.sqlite3
```

Для Timeweb лучше использовать PostgreSQL, чтобы данные игроков не терялись при пересоздании контейнера.

## Проверка Docker

```bash
docker build -t ner-talis-bot .
docker run --rm -p 8080:8080 --env-file .env ner-talis-bot
```

Проверка сайта:

```bash
curl http://localhost:8080/health
```

Должен вернуться ответ:

```text
OK
```

## Безопасность

Настоящий `.env` не загружай в GitHub. В репозитории должен быть только `.env.example`.

Если токен попал в логи или GitHub, перевыпусти его через BotFather/VK и обнови переменную окружения в Timeweb.
