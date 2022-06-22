import json
import os

_config_dir_path = os.path.expanduser("~/.config/paperoni")
_config_path = os.path.join(_config_dir_path, "config.json")


def _get_all_config():
    if not os.path.exists(_config_path):
        return None
    return json.load(open(_config_path))


def write_config(cfg):
    """Write the configuration file from the given dict."""
    os.makedirs(_config_dir_path, exist_ok=True)
    json.dump(cfg, open(_config_path, "w"))
    print(f"Wrote config in {_config_path}")


def get_config(key=None):
    """Get the value of the corresponding key in the configuration."""
    cfg = _get_all_config()
    if key is None:
        return cfg
    else:
        return cfg and cfg[key]
