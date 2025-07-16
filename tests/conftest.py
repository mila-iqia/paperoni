from pathlib import Path
from tempfile import TemporaryDirectory

import gifnoc
from pytest import fixture


@fixture(scope="session", autouse=True)
def set_config():
    with (
        gifnoc.use(Path(__file__).parent / "test-config.yaml"),
        TemporaryDirectory() as tmpdir,
    ):
        from paperoni.config import config

        config.data_path = Path(tmpdir) / "data"
        yield
