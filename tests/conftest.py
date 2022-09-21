import os
from pathlib import Path

from pytest import fixture


@fixture
def config():
    from paperoni.config import load_config

    restore = os.environ.get("PAPERONI_CONFIG", None)
    os.environ["PAPERONI_CONFIG"] = str(
        Path(__file__).parent / "data" / "config.yaml"
    )
    yield load_config()
    os.environ["PAPERONI_CONFIG"] = restore


@fixture
def database(config):
    from paperoni.config import load_database

    return load_database(config=config)
