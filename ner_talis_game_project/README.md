# Мир Нер-Талис — Telegram/VK bot prototype

Рабочий прототип кроссплатформенной текстовой RPG для Telegram и VK.

Основная игра проходит в ботах. Сайт используется как вспомогательная панель: профиль, торговый павильон, склад, аукцион и другие удобные интерфейсы.

## Что реализовано

- `/start`
- Reply-клавиатура Telegram
- клавиатура VK
- кнопки `Кратко о мире` и `Начать`
- регистрация персонажа
- проверка имени и уникальности
- выбор расы
- карточка расы
- подтверждение выбора
- создание персонажа
- единый `game_id` для Telegram и VK
- `/profile`
- `/link`
- `/connect КОД`
- `/city`
- город Селдар после регистрации
- переходы по кварталам Селдара
- торговый павильон через временную ссылку на сайт
- файл импорта стартовых данных

## Быстрый запуск

Команды ниже выполняются из корня репозитория.

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Установка зависимостей:

```bash
pip install -r ner_talis_game_project/requirements.txt
```

Создай `.env`:

```bash
cp .env.example .env
```

Код также подхватит `ner_talis_game_project/.env`, если такой файл уже используется локально.

Заполни токены Telegram и VK. Если запускаешь общий entrypoint, нужны оба токена и ID сообщества VK.

## Запуск обоих ботов одновременно

```bash
python ner_talis_game_project/main.py
```

`main.py` запускает VK-бота в отдельном потоке, а Telegram-бота — в основном потоке. Для этого в `.env` должны быть заполнены все три значения: `TELEGRAM_BOT_TOKEN`, `VK_GROUP_TOKEN`, `VK_GROUP_ID`.

## Запуск только Telegram

```bash
python ner_talis_game_project/main_telegram.py
```

## Запуск только VK

```bash
python ner_talis_game_project/main_vk.py
```

Для VK нужно включить сообщения сообщества и Long Poll API в настройках сообщества.

## Переменные окружения

```env
TELEGRAM_BOT_TOKEN=...
VK_GROUP_TOKEN=...
VK_GROUP_ID=...
SITE_PROFILE_BASE_URL=https://example.com/profile
SITE_PAVILION_URL=https://example.com/pavilion
PLAYERS_STORAGE_PATH=data/players.json
```

## Единый ID

Главный ID персонажа — `game_id`:

```text
NT-A1B2C3D4E5
```

Telegram ID и VK ID хранятся как привязки:

```json
{
  "game_id": "NT-A1B2C3D4E5",
  "linked_accounts": {
    "telegram": "123456789",
    "vk": "987654321"
  }
}
```

## Привязка аккаунтов

На платформе, где персонаж уже создан:

```text
/link
```

На второй платформе:

```text
/connect AB12CD
```

Код одноразовый и действует 15 минут.

## Город Селдар

После регистрации игрок получает кнопки:

```text
Профиль
В город
```

Кнопка `В город` или команда `/city` открывает Центральную площадь Селдара.

Главные разделы:

```text
- Портовый квартал
- Торговый квартал
- Ремесленный квартал
- Верхний квартал
- Городские ворота
- Объявления
```

## Файл импорта

Главный файл импорта:

```text
data/import_seed.json
```

Импортировать стартовые данные:

```bash
python ner_talis_game_project/tools/import_seed.py
```

Перезаписать `players.json` пустой схемой:

```bash
python ner_talis_game_project/tools/import_seed.py --overwrite-players
```

## Документация

```text
docs/PROJECT_STRUCTURE.md
docs/IMPORT_GUIDE.md
```


## Проверка работоспособности

```bash
python -m compileall -q .
python -m unittest discover -s ner_talis_game_project/tests
```

Smoke-test проверяет создание персонажа, уникальность имени, привязку Telegram/VK к одному `game_id`, вход в город Селдар и то, что общий запуск вызывает оба бота.
