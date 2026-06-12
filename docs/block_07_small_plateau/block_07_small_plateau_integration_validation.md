# Проверка интеграции Малого плато

- ✅ JSON-файлы Малого плато читаются
- ✅ События поиска Малого плато присутствуют: `events=27`
- ✅ Событие cursed_silver_coins есть
- ✅ Локация small_plateau описана: `small_plateau`
- ✅ Правила поиска: 2 энергии / 30 сек / 10 мин при 0 энергии: `{'mode': 'standard_external_location_search', 'energy_cost': 2, 'base_duration_seconds': 30, 'low_positive_energy_max_duration_seconds': 300, 'zero_energy_duration_seconds': 600, 'zero_energy_cost': 0, 'finish_event_table': 'small_plateau_search_events_v1', 'search_counter_key': 'small_plateau_search_count'}`
- ✅ Предметы old_brooch/old_medallion в items_small_plateau.json: `old_brooch,old_medallion`
- ✅ Ассеты броши/медальона существуют
- ✅ py_compile external_location_service/small_plateau_service
- ✅ Полный набор unittest пройден: `Ran 309 tests, OK (skipped=1)`
- ✅ Ошибок чтения runtime items_*.json нет
- ✅ Дубликатов item_id в runtime items_*.json нет: `{}`

## Тесты

`python -m unittest discover -s ner_talis_game_project/tests -v`

Результат: `309 tests run, OK, 1 skipped`.

## ZIP

- testzip: `None`
- duplicate entries: `0`