# Файл импорта

В проект добавлен файл:

```text
data/import_seed.json
```

Он нужен, чтобы хранить стартовые игровые данные в одном месте и переносить их между версиями проекта.

## Что внутри

```text
- meta                         # описание проекта
- races                        # расы
- cities.seldar                # город Селдар
- storage_schema               # пустая схема JSON-хранилища
- default_player_fields        # стартовые городские поля игрока
```

## Быстрый импорт

```bash
python tools/import_seed.py
```

Скрипт обновит:

```text
data/races.json
data/seldar_city.json
```

`data/players.json` по умолчанию не перезаписывается, чтобы не потерять игроков.

## Перезаписать игроков пустой схемой

Только для тестов или нового проекта:

```bash
python tools/import_seed.py --overwrite-players
```

## Импорт из другого файла

```bash
python tools/import_seed.py --file путь/к/файлу.json
```

## Отдельный файл для передачи

В архиве есть `data/import_seed.json`. Также отдельно приложен файл:

```text
ner_talis_import_seed.json
```

Его можно использовать как внешний файл импорта в будущую админку, сайт или миграцию в базу данных.
