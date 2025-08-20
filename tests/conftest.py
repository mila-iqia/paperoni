import os
from pathlib import Path
from tempfile import TemporaryDirectory

import gifnoc
from pytest import fixture
from serieux import Sources

# google.genai.Client needs a non-empty API key to initialize
os.environ["GOOGLE_API_KEY"] = "DUMMY_GOOGLE_API_KEY"


@fixture(scope="session", autouse=True)
def set_config():
    with TemporaryDirectory() as tmpdir:
        with gifnoc.use(
            Path(__file__).parent / "test-config.yaml",
            Sources({"paperoni.data_path": str(Path(tmpdir) / "data")}),
        ):
            yield
