# Проверка — Холмистые луга: таймеры, энергия и тексты поиска

## Точечная проверка

Запущены тесты:

```text
python3 -m unittest \
  ner_talis_game_project.tests.test_hilly_meadows_resources \
  ner_talis_game_project.tests.test_hilly_meadows_events \
  ner_talis_game_project.tests.test_hilly_meadows_mobs_drop \
  ner_talis_game_project.tests.test_hilly_meadows_search_timers_energy_texts -v
```

Результат:

```text
17 passed
```

## Полная проверка проекта

Запущен полный набор тестов:

```text
python3 -m unittest discover ner_talis_game_project/tests -v
```

Результат:

```text
279 tests run
278 passed
1 skipped
0 failed
```

Пропущенный тест связан с отсутствующими PostgreSQL-зависимостями в окружении тестирования и не относится к Холмистым лугам.

## ZIP-проверка

После сборки архива требуется проверка:

```text
zipfile.testzip() == None
```

Также проверяется отсутствие дубликатов записей ZIP.
