"""Импорт стартовых игровых данных из data/import_seed.json.

Скрипт нужен, чтобы быстро перенести общий файл импорта в рабочие JSON-файлы
проекта. Сейчас он импортирует расы, город Селдар, стартовую внешнюю
локацию «Холмистые луга» и пустую схему игроков.

Запуск:
    python ner_talis_game_project/tools/import_seed.py

По умолчанию существующий data/players.json не перезаписывается.
"""

import argparse
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_IMPORT_FILE = PROJECT_DATA_DIR / "import_seed.json"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def import_seed(import_file: Path, overwrite_players: bool = False) -> None:
    seed = read_json(import_file)

    races = seed.get("races")
    cities = seed.get("cities", {})
    external_locations = seed.get("external_locations", {})
    seldar = cities.get("seldar")
    hilly_meadows = external_locations.get("hilly_meadows")
    storage_schema = seed.get("storage_schema")
    items = seed.get("items", {})
    visual_assets = seed.get("item_visual_assets", {})
    schemas = seed.get("schemas", {})

    if not isinstance(races, dict):
        raise ValueError("В файле импорта отсутствует объект races.")
    if not isinstance(seldar, dict):
        raise ValueError("В файле импорта отсутствует город cities.seldar.")
    if not isinstance(hilly_meadows, dict):
        raise ValueError("В файле импорта отсутствует external_locations.hilly_meadows.")
    if not isinstance(storage_schema, dict):
        raise ValueError("В файле импорта отсутствует storage_schema.")

    write_json(PROJECT_DATA_DIR / "races.json", races)
    write_json(PROJECT_DATA_DIR / "seldar_city.json", seldar)
    write_json(PROJECT_DATA_DIR / "hilly_meadows.json", hilly_meadows)

    hilly_items = items.get("hilly_meadows") if isinstance(items, dict) else None
    if isinstance(hilly_items, list):
        write_json(PROJECT_DATA_DIR / "items_hilly_meadows.json", hilly_items)

    hilly_visual_assets = visual_assets.get("hilly_meadows") if isinstance(visual_assets, dict) else None
    if isinstance(hilly_visual_assets, dict):
        write_json(PROJECT_DATA_DIR / "item_visual_assets_hilly_meadows.json", hilly_visual_assets)

    pve_schema = schemas.get("pve_battle") if isinstance(schemas, dict) else None
    if isinstance(pve_schema, dict):
        write_json(PROJECT_DATA_DIR / "pve_battle_schema.json", pve_schema)

    players_path = PROJECT_DATA_DIR / "players.json"
    if overwrite_players or not players_path.exists():
        write_json(players_path, storage_schema)

    print("Импорт завершён:")
    print(f"- {PROJECT_DATA_DIR / 'races.json'}")
    print(f"- {PROJECT_DATA_DIR / 'seldar_city.json'}")
    print(f"- {PROJECT_DATA_DIR / 'hilly_meadows.json'}")
    if (PROJECT_DATA_DIR / "items_hilly_meadows.json").exists():
        print(f"- {PROJECT_DATA_DIR / 'items_hilly_meadows.json'}")
    if (PROJECT_DATA_DIR / "item_visual_assets_hilly_meadows.json").exists():
        print(f"- {PROJECT_DATA_DIR / 'item_visual_assets_hilly_meadows.json'}")
    if (PROJECT_DATA_DIR / "pve_battle_schema.json").exists():
        print(f"- {PROJECT_DATA_DIR / 'pve_battle_schema.json'}")
    if overwrite_players:
        print(f"- {players_path} перезаписан")
    else:
        print(f"- {players_path} не перезаписывался, если уже существовал")


def main() -> None:
    parser = argparse.ArgumentParser(description="Импорт стартовых данных Нер-Талис.")
    parser.add_argument(
        "--file",
        default=str(DEFAULT_IMPORT_FILE),
        help="Путь к JSON-файлу импорта.",
    )
    parser.add_argument(
        "--overwrite-players",
        action="store_true",
        help="Перезаписать data/players.json пустой схемой.",
    )
    args = parser.parse_args()

    import_seed(Path(args.file), overwrite_players=args.overwrite_players)


if __name__ == "__main__":
    main()
