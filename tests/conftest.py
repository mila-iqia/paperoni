from pathlib import Path
from tempfile import TemporaryDirectory

import gifnoc
from pytest import fixture
from serieux import Sources


@fixture(scope="session", autouse=True)
def set_config():
    with TemporaryDirectory() as tmpdir:
        with gifnoc.use(
            Path(__file__).parent / "test-config.yaml",
            Sources({"paperoni.data_path": str(Path(tmpdir) / "data")}),
        ):
            yield
