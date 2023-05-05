import os
from pathlib import Path
from . import utils

config = utils.load_config(
    Path(
        os.environ.get("GLU_CONFIG_PATH")
        or
        (Path(os.getcwd()) / "BotConfig.toml")
    )
)
