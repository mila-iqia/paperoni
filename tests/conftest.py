import os
from pathlib import Path
from tempfile import TemporaryDirectory

import gifnoc
from pytest import fixture

TESTS_PATH = Path(__file__).parent

# google.genai.Client needs a non-empty API key to initialize
os.environ["GEMINI_API_KEY"] = "DUMMY_GEMINI_API_KEY"
os.environ.pop("GOOGLE_API_KEY", None)


@fixture(scope="session")
def cfg_src():
    with TemporaryDirectory() as tmpdir:
        return [
            TESTS_PATH / "config/test-config.yaml",
            {"paperoni.data_path": str(Path(tmpdir) / "data")},
        ]


@fixture(scope="session", autouse=True)
def set_config(cfg_src: list[str | dict]):
    with gifnoc.use(*cfg_src):
        yield
