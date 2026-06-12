# Проверка — Холмистые луга: пересборка событий

## Автопроверки

- ZIP `testzip`: `None`
- Дубликаты ZIP-записей: `0`
- Сумма весов событий Холмистых лугов: `100`
- `waterside_loot` в `data/hilly_meadows.json/events`: `нет`
- JSON `data/hilly_meadows.json`: читается без ошибок

## Тесты

Запущены точечные тесты:

```text
python -m pytest ner_talis_game_project/tests/test_hilly_meadows_events.py ner_talis_game_project/tests/test_hilly_meadows_resources.py -q
```

Результат:

```text
==================================== ERRORS ====================================
__ ERROR collecting ner_talis_game_project/tests/test_hilly_meadows_events.py __
/opt/pyvenv/lib/python3.13/site-packages/_pytest/python.py:507: in importtestmodule
    mod = import_path(
/opt/pyvenv/lib/python3.13/site-packages/_pytest/pathlib.py:587: in import_path
    importlib.import_module(module_name)
/usr/lib/python3.13/importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
<frozen importlib._bootstrap>:1331: in _find_and_load_unlocked
    ???
<frozen importlib._bootstrap>:935: in _load_unlocked
    ???
/opt/pyvenv/lib/python3.13/site-packages/_pytest/assertion/rewrite.py:197: in exec_module
    exec(co, module.__dict__)
ner_talis_game_project/tests/test_hilly_meadows_events.py:12: in <module>
    from services.external_location_service import START_SEARCH, create_search_event, handle_external_location_action
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
<frozen importlib._bootstrap>:1331: in _find_and_load_unlocked
    ???
<frozen importlib._bootstrap>:935: in _load_unlocked
    ???
<frozen importlib._bootstrap_external>:1022: in exec_module
    ???
/opt/pyvenv/lib/python3.13/site-packages/ddtrace/internal/module.py:291: in get_code
    code = _get_code(fullname)
           ^^^^^^^^^^^^^^^^^^^
E     File "/mnt/data/hm_events_test_extract/ner_talis-main/ner_talis_game_project/services/external_location_service.py", line 1503
E       return f"Поднявшись выше по склону, вы замечаете нож, воткнутый в землю. Скорее всего, кто-то пытался замедлить спуск вниз по траве, но вышло не слишком удачно.
E              ^
E   SyntaxError: unterminated f-string literal (detected at line 1503)
_ ERROR collecting ner_talis_game_project/tests/test_hilly_meadows_resources.py _
/opt/pyvenv/lib/python3.13/site-packages/_pytest/python.py:507: in importtestmodule
    mod = import_path(
/opt/pyvenv/lib/python3.13/site-packages/_pytest/pathlib.py:587: in import_path
    importlib.import_module(module_name)
/usr/lib/python3.13/importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
<frozen importlib._bootstrap>:1331: in _find_and_load_unlocked
    ???
<frozen importlib._bootstrap>:935: in _load_unlocked
    ???
/opt/pyvenv/lib/python3.13/site-packages/_pytest/assertion/rewrite.py:197: in exec_module
    exec(co, module.__dict__)
ner_talis_game_project/tests/test_hilly_meadows_resources.py:12: in <module>
    from services.external_location_service import (
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
<frozen importlib._bootstrap>:1331: in _find_and_load_unlocked
    ???
<frozen importlib._bootstrap>:935: in _load_unlocked
    ???
<frozen importlib._bootstrap_external>:1022: in exec_module
    ???
/opt/pyvenv/lib/python3.13/site-packages/ddtrace/internal/module.py:291: in get_code
    code = _get_code(fullname)
           ^^^^^^^^^^^^^^^^^^^
E     File "/mnt/data/hm_events_test_extract/ner_talis-main/ner_talis_game_project/services/external_location_service.py", line 1503
E       return f"Поднявшись выше по склону, вы замечаете нож, воткнутый в землю. Скорее всего, кто-то пытался замедлить спуск вниз по траве, но вышло не слишком удачно.
E              ^
E   SyntaxError: unterminated f-string literal (detected at line 1503)
=========================== short test summary info ============================
ERROR ner_talis_game_project/tests/test_hilly_meadows_events.py
ERROR ner_talis_game_project/tests/test_hilly_meadows_resources.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
2 errors in 0.34s
```


## Дополнительно

- Код возврата pytest: `2`
- Пропущено при тестовом извлечении из-за ограничений ФС: `2` служебных/документных файлов.
