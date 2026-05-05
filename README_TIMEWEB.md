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
└─ ner_talis_game_project/
   ├─ requirements.txt
   ├─ main.py
   ├─ main_telegram.py
   ├─ main_vk.py
   ├─ handlers/
   ├─ services/
   ├─ storage/
   ├─ keyboards/
   └─ texts/
```

## Что делает обновление

- `Dockerfile` собирает Python 3.12 контейнер.
- `Dockerfile` содержит `HEALTHCHECK`, который проверяет `/health` через Python без `curl`.
- `timeweb_start.py` поднимает маленький HTTP-сервер на `PORT=8080` для проверки контейнера и запускает `ner_talis_game_project/main.py`.
- `/health` всегда проверяет, что контейнер жив и слушает порт. `/ready` показывает состояние ботов и вернёт `503`, если бот упал из-за токена или другой ошибки.
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
BOT_MODE=both
LOG_LEVEL=INFO
PORT=8080
PLAYERS_STORAGE_PATH=data/players.json
SITE_PROFILE_BASE_URL=https://your-domain.ru/profile
SITE_PAVILION_URL=https://your-domain.ru/pavilion
```

`BOT_MODE` может быть `both`, `telegram` или `vk`. Если запускаешь только Telegram-бота, выставь `BOT_MODE=telegram` и можно не задавать VK-переменные. Для `both` нужны все три токен-переменные.

Если токен попал в логи, перевыпусти его через BotFather и обнови переменную окружения в Timeweb.

Важно: JSON-хранилище игроков внутри контейнера подходит для прототипа. При пересоздании контейнера App Platform локальный файл может потеряться. Для продакшена лучше вынести игроков в управляемую БД или другое постоянное хранилище.

## Локальная проверка Docker

```bash
docker build -t ner-talis-bot .
docker run --rm -p 8080:8080 --env-file ner_talis_game_project/.env ner-talis-bot
```

Проверка health endpoint:

```bash
curl http://localhost:8080/health
curl http://localhost:8080/ready
```

Должен вернуться ответ:

```text
OK
```
