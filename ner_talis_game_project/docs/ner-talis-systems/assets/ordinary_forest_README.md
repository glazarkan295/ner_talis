# Нер-Талис — ассеты для локации «Обыкновенный лес»

В пакете подготовлены 30 отдельных PNG-иконок для интеграции в проект.

## Что внутри

- `assets/items/ordinary_forest/...` — основные PNG 512×512 с прозрачным фоном.
- `assets_1024/items/ordinary_forest/...` — крупные PNG 1024×1024 для профиля/сайта.
- `assets_256/items/ordinary_forest/...` — лёгкие PNG 256×256 для быстрых списков и бота.
- `atlas_ordinary_forest.png` + `atlas_ordinary_forest.json` — общий атлас 512×512 по 30 ячейкам.
- `item_visual_assets.ordinary_forest.json` — полный манифест ассетов.
- `items_import.ordinary_forest.json` — упрощённый файл для импорта предметов.
- `item_assets_ordinary_forest.py` — Python-реестр.
- `itemAssetsOrdinaryForest.js` — JS-реестр.
- `preview/contact_sheet_ordinary_forest.jpg` — предпросмотр.
- `source_sheets/` — исходная общая картинка, по которой проверялась раскладка ассетов.

## Рекомендация по использованию

Для сайта лучше использовать файлы из `assets/items/ordinary_forest/`.
Для маленьких кнопок Telegram/VK — `assets_256/`.
Для спрайтового UI — `atlas_ordinary_forest.png` и координаты из `atlas_ordinary_forest.json`.

Все файлы переименованы английскими `id`, а русские названия лежат в JSON-манифестах.
