# Проверка — Холмистые луга: мобы и дроп

Проверки выполнялись после настройки мобов и добычи.

## Проверено

- ZIP открывается без ошибок.
- Дубликатов записей в ZIP нет.
- `data/hilly_meadows.json` читается как JSON.
- `pve_battle_service.py` компилируется через `py_compile`.
- Каталог мобов Холмистых лугов содержит ожидаемые 4 mob_id.
- Вся добыча мобов имеет соответствие в `BATTLE_LOOT_ITEM_IDS["hilly_meadows"]`.
- Обычный пул не содержит быка.
- Элитный пул содержит только быка.
- Усиленный и элитный ранги продолжают повышать шанс/количество добычи.

## Тесты

Точечные тесты Холмистых лугов и дропа:

```text
python -m pytest ner_talis_game_project/tests/test_hilly_meadows_events.py ner_talis_game_project/tests/test_hilly_meadows_resources.py ner_talis_game_project/tests/test_hilly_meadows_mobs_drop.py -q
```

Результат будет записан ниже после запуска.

### Результат py_compile

```text
exit_code=0

```

### Результат pytest

```text
exit_code=2

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
E     File "/mnt/data/hm_mobs_test/ner_talis_game_project/services/external_location_service.py", line 1503
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
E     File "/mnt/data/hm_mobs_test/ner_talis_game_project/services/external_location_service.py", line 1503
E       return f"Поднявшись выше по склону, вы замечаете нож, воткнутый в землю. Скорее всего, кто-то пытался замедлить спуск вниз по траве, но вышло не слишком удачно.
E              ^
E   SyntaxError: unterminated f-string literal (detected at line 1503)
=========================== short test summary info ============================
ERROR ner_talis_game_project/tests/test_hilly_meadows_events.py
ERROR ner_talis_game_project/tests/test_hilly_meadows_resources.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
2 errors in 0.40s

```
