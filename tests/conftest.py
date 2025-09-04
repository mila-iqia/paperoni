import os
from pathlib import Path
from tempfile import TemporaryDirectory

import gifnoc
from pytest import fixture

TESTS_PATH = Path(__file__).parent

# google.genai.Client needs a non-empty API key to initialize
os.environ["GEMINI_API_KEY"] = "DUMMY_GEMINI_API_KEY"
os.environ.pop("GOOGLE_API_KEY", None)


@fixture(scope="session", autouse=True)
def set_config():
    with TemporaryDirectory() as tmpdir:
        with gifnoc.use(
            TESTS_PATH / "config/test-config.yaml",
            {"paperoni.data_path": str(Path(tmpdir) / "data")},
        ):
            yield
