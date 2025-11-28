import tempfile
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from unittest.mock import patch

import gifnoc
import pytest
from easy_oauth.testing.utils import AppTester


@contextmanager
def _wrap(cfg_src: list[str | dict]):
    from paperoni.config import config

    tmp_path = Path(tempfile.mkdtemp())
    additional = {
        "paperoni.work_file": str(tmp_path / "work.yaml"),
        "paperoni.collection.$class": "paperoni.collection.memcoll:MemCollection",
    }
    with gifnoc.use(*cfg_src, additional):
        with patch("paperoni.web.restapi.config.metadata") as mock_meta:
            mock_meta.focuses.file = config.work_file.parent / "focuses.yaml"
            mock_meta.focuses.file.write_text("[]")
            yield


@pytest.fixture(scope="session")
def app(oauth_mock, cfg_src):
    from paperoni.web import create_app

    with AppTester(create_app(), oauth_mock, wrap=partial(_wrap, cfg_src)) as appt:
        yield appt


@pytest.fixture
def app_factory(oauth_mock, cfg_src):
    from paperoni.web import create_app

    @contextmanager
    def make(overlay):
        with AppTester(
            create_app(), oauth_mock, wrap=partial(_wrap, [*cfg_src, overlay])
        ) as appt:
            yield appt

    yield make
