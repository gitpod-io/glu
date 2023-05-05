from typing import Any
from tomllib import load as toml_load
from pathlib import Path


def load_config(path: Path) -> dict[str, Any]:
    config_file = open(path, "rb")
    config = toml_load(config_file)
    config_file.close()
    return config
