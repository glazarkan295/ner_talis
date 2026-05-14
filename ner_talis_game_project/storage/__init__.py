from storage.base import PlayerStorage
from storage.hard_delete_runtime import patch_known_storage_classes
from storage.storage_factory import create_storage

patch_known_storage_classes()

__all__ = ["PlayerStorage", "create_storage"]
