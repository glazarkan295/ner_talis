# Блок 7 — Обыкновенный лес: проверка таймеров, энергии и текстов поиска

## Проверки

- `py_compile external_location_service.py` — успешно.
- `py_compile pve_battle_service.py` — успешно.
- Точечные тесты Обыкновенного леса/Холмистых лугов/таймеров: **28 tests OK**.
- Полный набор тестов проекта: **302 tests run, OK, 1 skipped**.
- Проверка ZIP: `testzip None`.
- Дубликаты ZIP-записей: **0**.

## Команды проверки

```bash
python3 -m py_compile ner_talis_game_project/services/external_location_service.py ner_talis_game_project/services/pve_battle_service.py
python3 -m unittest   ner_talis_game_project.tests.test_ordinary_forest_search_timers_energy_texts   ner_talis_game_project.tests.test_ordinary_forest_resources   ner_talis_game_project.tests.test_ordinary_forest_events   ner_talis_game_project.tests.test_ordinary_forest_mobs_drop   ner_talis_game_project.tests.test_hilly_meadows_search_timers_energy_texts
python3 -m unittest discover -s ner_talis_game_project/tests
```

## Итог

Локация **Обыкновенный лес** теперь имеет такие же явные правила поиска, как Холмистые луга: 2 энергии, 30 секунд при полной энергии, максимум 5 минут при низкой положительной энергии и 10 минут при 0 энергии.
