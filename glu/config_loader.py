import os
import sys
from pathlib import Path
import glu.utils as utils

# Check if a command-line argument is provided
if len(sys.argv) > 1:
    config_path = Path(sys.argv[1])
else:
    config_path = Path(
        os.environ.get("GLU_CONFIG_PATH")
        or
        (Path(os.getcwd()) / "BotConfig.toml")
    )

config = utils.load_config(config_path)
