from pathlib import Path

import pytest
from pytest_regressions.file_regression import FileRegressionFixture

from paperoni.discovery.jmlr import JMLR

from ..utils import check_papers


@pytest.fixture(autouse=True)
def cache_dir(tmpdir):
    _cache_dir = Path(tmpdir).parent.parent
    discoverer = JMLR()
    assert "v24" in discoverer.list_volumes()
    next(discoverer.get_volume("v24", cache=_cache_dir))
    yield _cache_dir


def test_query(cache_dir, file_regression: FileRegressionFixture):
    discoverer = JMLR()

    papers = sorted(
        discoverer.query(volume="v24", name="Yoshua Bengio", cache=cache_dir),
        key=lambda x: x.title,
    )

    check_papers(file_regression, papers)
