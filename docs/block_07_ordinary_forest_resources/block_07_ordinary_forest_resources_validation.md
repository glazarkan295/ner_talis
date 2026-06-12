# Проверка — Обыкновенный лес: ресурсы и находки

## Проверенные пункты

- `data/ordinary_forest.json` содержит `resource_find_tables_version = ordinary_forest_resources_v1`.
- В `resource_find_tables` есть таблицы:
  - `dry_tree`
  - `mushrooms`
  - `river_water`
  - `small_burrow`
- `waterside_loot` отсутствует в событиях Обыкновенного леса.
- Событие сухого дерева выдаёт **Сухое бревно**.
- Событие грибов выдаёт один из настроенных грибов.
- Событие речушки выдаёт **Чистую воду** и дополнительные водные находки по таблице.
- Событие норы выдаёт старые перчатки, куски ткани, неплохой пояс или укус.

## Команды проверки

```text
python -m py_compile ner_talis_game_project/services/external_location_service.py
python -m unittest ner_talis_game_project.tests.test_ordinary_forest_resources ner_talis_game_project.tests.test_block7_locations_fishing ner_talis_game_project.tests.test_hilly_meadows_search_timers_energy_texts
python -m unittest discover ner_talis_game_project/tests
```

## Результат

```text
py_compile: OK
targeted tests: 17 passed
full tests: 284 tests run, 283 passed, 1 skipped, 0 failed
zip testzip: None
zip duplicate entries: 0
```

Примечание: предупреждение `Spreadsheet runtime warmup failed during python startup` относится к окружению исполнения и не ломает тесты проекта.
