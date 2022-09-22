from pathlib import Path

from pytest import fixture


@fixture
def config():
    from paperoni.config import load_config

    default_config = Path(__file__).parent / "data" / "config.yaml"
    with load_config(default_config) as cfg:
        yield cfg


@fixture
def transient_config():
    from paperoni.config import load_config

    transient = Path(__file__).parent / "data" / "transient-config.yaml"
    with load_config(transient) as cfg:
        dbf = cfg.paths.database
        if dbf.exists():
            dbf.unlink()
        yield cfg


@fixture
def database(config):
    return config.database
