# Timeweb Cloud + PostgreSQL для Нер-Талис

В этой версии проект рассчитан на PostgreSQL как основное production-хранилище.

## Главные переменные

```env
STORAGE_BACKEND=postgres
DATABASE_URL=postgresql://POSTGRES_USER:POSTGRES_PASSWORD@POSTGRES_HOST:5432/POSTGRES_DB
APP_ENV=production
```

В Timeweb значение `DATABASE_URL` вставляй без `DATABASE_URL=` и без кавычек.

Правильно:

```text
postgresql://user:password@host:5432/db_name
```

Неправильно:

```text
DATABASE_URL=postgresql://user:password@host:5432/db_name
'postgresql://user:password@host:5432/db_name'
```

## Что хранится в PostgreSQL

PostgreSQL хранит:

- игроков;
- привязки Telegram/VK;
- одноразовые токены профиля;
- активные web-сессии профиля;
- одноразовые токены и сессии админ-панели;
- промокоды.

`data/players.json` больше не должен быть основной базой. Он используется только как legacy-файл для автопереноса, если есть старые данные.

## Автообновление схемы

При старте `PostgresStorage` создаёт недостающие таблицы и безопасно добавляет недостающие колонки через `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. Это нужно для случаев, когда в Timeweb уже есть старая PostgreSQL-база от предыдущего архива.

## Runtime uploads

Загруженные через админку изображения предметов не хранятся в PostgreSQL. Они сохраняются в:

```text
data/public_uploads/assets/admin_uploads/items/...
```

Для Timeweb эту директорию нужно сделать постоянной через volume/диск. Иначе после пересборки/перезапуска контейнера загруженные картинки могут исчезнуть.

## Проверка после деплоя

Открой:

```text
https://ner-talis-game.ru/health
https://ner-talis-game.ru/ready
```

`/health` проверяет, что контейнер жив.

`/ready` проверяет, что приложение смогло подключиться к PostgreSQL.

Если `/ready` вернул `503`, почти всегда проблема в `STORAGE_BACKEND`, `DATABASE_URL`, доступе к базе или неправильном пароле.
