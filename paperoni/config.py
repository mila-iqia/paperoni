import os
from pathlib import Path
from types import SimpleNamespace

from coleo import config as configuration
from ovld import ovld

config = SimpleNamespace()
scrapers = {}


@ovld
def configure(config_file: str):
    root = Path(config_file).parent
    cfg = configuration(config_file)
    cfg["root"] = root
    configure(cfg)


@ovld
def configure(cfg: dict):
    global config
    root = Path(cfg.get("root", os.curdir))
    for k, v in cfg.items():
        if k.endswith("_file"):
            if not v.startswith("/"):
                cfg[k] = str(root / v)
    config.__dict__.update(cfg)
