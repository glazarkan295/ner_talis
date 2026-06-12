# Блок 7 — Обыкновенный лес: событие «Небольшая нора»

Источник: `ner_talis-main-51-block7-ordinary-forest-resources-updated.zip`.

## Что изменено

Событие `small_burrow` обновлено по новым шансам:

| Исход | Шанс/вес |
|---|---:|
| Старые перчатки (необычные) | 12% |
| Куски ткани | 36% |
| Неплохой пояс (необычные) | 12% |
| Укус из норы | 40% |

## Обновлённые предметы

### Старые перчатки (необычные)

- `item_id`: `old_gloves`
- категория: перчатки
- инвентарь: снаряжение
- слот: перчатки
- покупка: нет
- базовая продажа: 300 медных
- источник: события локаций / Обыкновенный лес
- стак: 1
- эффект: `+X` к ловкости и `+X,X%` к шансу крита; сила зависит мягко от уровня игрока, нашедшего предмет.

Технически для runtime добавлена формула найденного предмета:
- `bonus_agility = floor(1 + 0.08 * sqrt(player_level))`
- отображаемый шанс крита: `round(0.5 + 0.03 * sqrt(player_level), 1)%`

### Неплохой пояс (необычные)

- `item_id`: `decent_belt`
- категория: пояс
- инвентарь: снаряжение
- слот: пояс
- покупка: нет
- базовая продажа: 300 медных
- источник: события локаций / Обыкновенный лес
- стак: 1
- эффект: `+2` слота инвентаря, `+X` к броне, `+X` к уклонению; сила брони/уклонения зависит мягко от уровня игрока, нашедшего предмет.

Технически для runtime добавлена формула найденного предмета:
- `inventory_slots_bonus = 2`
- `armor = floor(1 + 0.10 * sqrt(player_level))`
- `bonus_dodge = floor(1 + 0.08 * sqrt(player_level))`

## Файлы

- `data/ordinary_forest.json`
- `data/items_ordinary_forest.json`
- `data/item_visual_assets_ordinary_forest.json`
- `data/item_sell_prices.json`
- `ner_talis_game_project/services/external_location_service.py`
- `ner_talis_game_project/services/inventory_service.py`
- `web/public/assets*/items/ordinary_forest/equipment/old_gloves.png`
- `web/public/assets*/items/ordinary_forest/equipment/decent_belt.png`

## Замечание

Для `old_gloves` и `decent_belt` сохранены прежние `item_id`, чтобы не ломать старые сохранения и ссылки. Названия и качество обновлены до необычных.
