import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from coleo import config as configuration
from ovld import ovld

config = SimpleNamespace()


@ovld
def configure(**extra_config):
    return configure(None, **extra_config)


@ovld
def configure(config: None, **extra_config):
    config = os.getenv("PAPERONI_CONFIG")
    if not config:
        exit("No configuration could be found.")
    return configure(config, **extra_config)


@ovld
def configure(config_file: str, **extra_config):
    root = Path(config_file).parent
    cfg = configuration(config_file)
    cfg["root"] = root
    cfg.update(extra_config)
    return configure(cfg)


@ovld
def configure(cfg: dict):
    global config
    root = Path(cfg.get("root", os.curdir))
    for k, v in cfg.items():
        if k.endswith("_file") or k.endswith("_root"):
            if not v.startswith("/"):
                cfg[k] = str(root / v)
    if "history_file" not in cfg:
        hroot = cfg["history_root"]
        os.makedirs(hroot, exist_ok=True)
        now = datetime.now().strftime("%Y-%m-%d-%s")
        tag = cfg.get("tag", "")
        tag = tag and f"-{tag}"
        hfile = Path(hroot) / f"{now}{tag}.jsonl"
        cfg["history_file"] = hfile
    config.__dict__.update(cfg)
    return config
