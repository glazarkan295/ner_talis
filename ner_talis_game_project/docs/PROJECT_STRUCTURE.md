# Структура проекта «Мир Нер-Талис»

Проект сейчас собран как ранний рабочий прототип для Telegram и VK. Основная игра проходит в ботах, а сайт используется как вспомогательная панель: профиль, торговый павильон, склад, аукцион и другие удобные интерфейсы.

## Общий принцип

```text
Telegram / VK
    ↓
handlers платформы
    ↓
services общего ядра
    ↓
storage/json_storage.py
    ↓
data/players.json
```

Главный идентификатор игрока — `game_id`. Telegram ID и VK ID являются только привязками к одному персонажу.

## Папки

```text
ner_talis_game_project/
├── main.py                         # Общий запуск Telegram + VK
├── main_telegram.py                # Запуск только Telegram-бота
├── main_vk.py                      # Запуск только VK-бота
├── requirements.txt                # Python-зависимости
├── .env.example                    # Пример переменных окружения
│
├── data/
│   ├── races.json                  # Расы и стартовые характеристики
│   ├── seldar_city.json            # Техническая карта города Селдар
│   ├── import_seed.json            # Единый файл импорта стартовых данных
│   └── players.empty.json          # Пустой шаблон хранилища игроков
│
├── handlers/
│   ├── registration.py             # Telegram-регистрация и команды профиля/связки
│   ├── vk_registration.py          # VK-регистрация, команды и городские действия
│   └── city.py                     # Telegram-городские действия
│
├── keyboards/
│   ├── reply_keyboards.py          # Reply-клавиатуры Telegram
│   └── vk_keyboards.py             # Клавиатуры VK
│
├── services/
│   ├── registration_service.py     # Общая логика имени, рас и создания персонажа
│   └── city_service.py             # Общая логика города Селдар
│
├── storage/
│   └── json_storage.py             # JSON-хранилище, game_id, /link, /connect, site-сессии
│
├── texts/
│   └── registration_texts.py       # Тексты регистрации и вступления
│
├── tools/
│   └── import_seed.py              # Импорт стартовых данных из import_seed.json
│
├── tests/
│   └── smoke_test.py               # Проверка регистрации, связки платформ, города и общего запуска
│
└── docs/
    ├── PROJECT_STRUCTURE.md        # Этот файл
    └── IMPORT_GUIDE.md             # Как пользоваться файлом импорта
```

## Основной игровой путь

```text
/start
→ Кратко о мире / Начать
→ ввод имени
→ проверка уникальности имени
→ выбор расы
→ карточка расы
→ Выбрать / Назад
→ Да / Нет
→ создание персонажа
→ Профиль / В город
→ Центральная площадь Селдара
```

## Единый игровой ID

При создании персонажа создаётся `game_id`, например:

```text
NT-A1B2C3D4E5
```

В профиле игрока это хранится так:

```json
{
  "game_id": "NT-A1B2C3D4E5",
  "linked_accounts": {
    "telegram": "123456789",
    "vk": "987654321"
  }
}
```

## Привязка Telegram и VK

```text
/link
```

Создаёт одноразовый код на 15 минут.

```text
/connect AB12CD
```

Привязывает текущую платформу к уже существующему персонажу.

## Город Селдар

После регистрации игрок попадает в Селдар. Стартовая зона:

```text
seldar_central_square
```

Главные разделы города:

```text
- Центральная площадь
- Портовый квартал
- Торговый квартал
- Ремесленный квартал
- Верхний квартал
- Городские ворота
```

Торговый павильон в боте не разворачивает сложное меню. Бот создаёт короткоживущую site-сессию и выдаёт ссылку на сайт.

## Где добавлять следующие системы

```text
Бой:                    services/combat_service.py + handlers/combat.py
Локации вне города:     services/location_service.py + data/locations.json
Инвентарь:              services/inventory_service.py
Экономика:              services/economy_service.py
Крафт:                  services/crafting_service.py
Алхимия:                services/alchemy_service.py
Сайт/API:               site_api/ или отдельный FastAPI-проект
```
