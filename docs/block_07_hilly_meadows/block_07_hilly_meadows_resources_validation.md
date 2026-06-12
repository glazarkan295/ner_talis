# Проверка блока 7 — Холмистые луга: ресурсы/находки

- ZIP `testzip`: `None`
- Дубликаты записей ZIP: 0
- Точечный тест: `test_hilly_meadows_resources.py`
- Код возврата теста: 2

## stdout

```text
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.0.2, pluggy-1.6.0
rootdir: /mnt/data/hilly_meadows_resources_test/ner_talis-main/ner_talis_game_project
plugins: Faker-40.1.2, metadata-3.1.1, ddtrace-4.4.0, anyio-4.13.0, cov-7.0.0, asyncio-1.3.0, json-report-1.5.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 0 items / 1 error

==================================== ERRORS ====================================
____________ ERROR collecting tests/test_hilly_meadows_resources.py ____________
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
tests/test_hilly_meadows_resources.py:12: in <module>
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
E     File "/mnt/data/hilly_meadows_resources_test/ner_talis-main/ner_talis_game_project/services/external_location_service.py", line 1451
E       return f"Поднявшись выше по склону, вы замечаете нож, воткнутый в землю. Скорее всего, кто-то пытался замедлить спуск вниз по траве, но вышло не слишком удачно.
E              ^
E   SyntaxError: unterminated f-string literal (detected at line 1451)
=========================== short test summary info ============================
ERROR tests/test_hilly_meadows_resources.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.37s ===============================
```

## stderr

```text

```
