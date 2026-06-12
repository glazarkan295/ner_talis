# Проверка блока 08 — Крепость в ущелье, шаг 1

## Проверено

- Python-компиляция изменённых файлов.
- JSON-файлы читаются.
- Новый предмет `evidence_bag` регистрируется через общий `item_registry`.
- Ассет мешка с доказательством существует в публичных путях.
- Навигация по Крепости в ущелье работает через `handle_external_location_action(...)`.
- Меню Координатора и Доски заказов открываются.
- `evidence_bag` стакается только по одному и тому же игроку-жертве.
- Мешки с доказательствами от разных игроков не объединяются в один стак.
- Старые проверки штрафов/Крепостной Ратуши не сломаны.

## Команды проверки

```bash
python -m pytest ner_talis_game_project/tests/test_fortress_in_gorge_step1.py -q
python -m pytest ner_talis_game_project/tests/test_fortress_in_gorge_step1.py ner_talis_game_project/tests/test_black_market_raid_fines.py ner_talis_game_project/tests/test_ordinary_forest_search_timers_energy_texts.py ner_talis_game_project/tests/test_small_plateau_integration.py -q
python -m pytest ner_talis_game_project/tests -q
```

## Результаты

- Точечный тест Крепости: `3 passed`
- Связанные тесты: `21 passed`
- Полный набор проекта: `311 passed, 1 skipped, 249 subtests passed`
- ZIP `testzip`: `None`
- Дубликатов ZIP-записей: `0`

## Замечания

Сообщение `Spreadsheet runtime warmup failed...` появляется в stderr окружения при запуске Python, но не влияет на тесты проекта: pytest завершился с кодом `0`.
