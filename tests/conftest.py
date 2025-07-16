from pathlib import Path

import gifnoc
from pytest import fixture


@fixture(scope="session", autouse=True)
def set_config():
    with gifnoc.use(Path(__file__).parent / "test-config.yaml"):
        yield
