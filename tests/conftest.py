import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import gifnoc
import pytest
from easy_oauth.testing.utils import OAuthMock
from ovld import Medley, call_next, ovld
from pytest import fixture
from serieux import Context, Serieux, deserialize, serialize
from serieux.priority import HI1

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


class RegressionRules(Medley):
    omissions: dict

    @ovld(priority=HI1)
    def serialize(self, t: Any, obj: Any, ctx: Context):
        result = call_next(t, obj, ctx)
        if isinstance(result, dict):
            for field in self.omissions.get(t, set()):
                result.pop(field, None)
        return result

    @ovld(priority=HI1)
    def serialize(self, t: type[set[Any]], obj: Any, ctx: Context):
        return sorted(call_next(t, obj, ctx))


@pytest.fixture
def dreg(data_regression):
    from paperoni.model import Paper

    omissions = {Paper: {"id", "version", "score"}}
    srx = (Serieux + RegressionRules)(omissions=omissions)

    @ovld
    def regress(x):
        regress(type(x), x)

    @ovld
    def regress(t, obj):
        # Check roundtrip
        assert deserialize(t, serialize(t, obj)) == obj

        data = srx.serialize(t, obj)
        data_regression.check(data)

    return regress
