import logging
import os

from handlers.vk_registration import VkRegistrationBot
from project_paths import load_project_env, resolve_project_path


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


def main() -> None:
    load_project_env()

    token = os.getenv("VK_GROUP_TOKEN")
    group_id = os.getenv("VK_GROUP_ID")
    storage_path = str(resolve_project_path(os.getenv("PLAYERS_STORAGE_PATH", "data/players.json")))

    if not token:
        raise RuntimeError("Не указан VK_GROUP_TOKEN в .env")

    if not group_id:
        raise RuntimeError("Не указан VK_GROUP_ID в .env")

    bot = VkRegistrationBot(
        token=token,
        group_id=int(group_id),
        storage_path=storage_path,
    )
    bot.run()


if __name__ == "__main__":
    main()
