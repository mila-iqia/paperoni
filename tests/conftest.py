import os
from pathlib import Path
from tempfile import TemporaryDirectory

import gifnoc
import pytest
from easy_oauth.testing.utils import OAuthMock
from pytest import fixture

TESTS_PATH = Path(__file__).parent

# google.genai.Client needs a non-empty API key to initialize
os.environ["GEMINI_API_KEY"] = "DUMMY_GEMINI_API_KEY"
os.environ.pop("GOOGLE_API_KEY", None)
os.environ.pop("GIFNOC_FILE", None)


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


OAUTH_PORT = 29313


@pytest.fixture(scope="session")
def oauth_mock():
    with OAuthMock(port=OAUTH_PORT) as oauth:
        yield oauth
