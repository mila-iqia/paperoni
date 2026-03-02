import shutil
import tempfile
from contextlib import contextmanager
from functools import partial
from pathlib import Path

import gifnoc
import pytest
from easy_oauth.testing.utils import AppTester
from serieux.features.partial import Override

here = Path(__file__).parent


@contextmanager
def _wrap(cfg_src: list[str | dict], collfile):
    tmp_path = Path(tempfile.mkdtemp())
    additional = {
        "paperoni.work_file": str(tmp_path / "work.yaml"),
        "paperoni.collection": {
            "$class": "paperoni.collection.filecoll:FileCollection",
            "file": str(collfile),
        },
        "paperoni.focuses": Override(str(tmp_path / "focuses.yaml")),
    }
    with gifnoc.use(*cfg_src, additional):
        yield


@pytest.fixture(scope="session")
def app(oauth_mock, cfg_src):
    from paperoni.web import create_app

    collfile = here / ".." / "data" / "papers.yaml"
    # Make sure the file is read-only
    collfile.chmod(0o444)
    with AppTester(
        create_app(), oauth_mock, wrap=partial(_wrap, cfg_src, collfile)
    ) as appt:
        yield appt


@pytest.fixture(scope="function")
def wr_app(oauth_mock, cfg_src, tmp_path):
    from paperoni.web import create_app

    src_collfile = here / ".." / "data" / "papers.yaml"
    collfile = tmp_path / "papers.yaml"
    shutil.copy(str(src_collfile), str(collfile))
    # Make sure the file is read-writable
    collfile.chmod(0o666)
    with AppTester(
        create_app(), oauth_mock, wrap=partial(_wrap, cfg_src, collfile)
    ) as appt:
        yield appt


@pytest.fixture
def app_factory(oauth_mock, cfg_src):
    from paperoni.web import create_app

    @contextmanager
    def make(overlay):
        collfile = here / ".." / "data" / "papers.yaml"
        with AppTester(
            create_app(), oauth_mock, wrap=partial(_wrap, [*cfg_src, overlay], collfile)
        ) as appt:
            yield appt

    yield make
