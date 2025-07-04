from pathlib import Path

import pytest
from serieux import serialize

from paperoni.discovery.jmlr import JMLR
from paperoni.model.classes import Paper

from ..utils import sort_keys


@pytest.fixture(autouse=True)
def cache_dir(tmpdir):
    _cache_dir = Path(tmpdir).parent.parent
    discoverer = JMLR()
    assert "v24" in discoverer.list_volumes()
    next(discoverer.get_volume("v24", cache=_cache_dir))
    yield _cache_dir


def test_query(cache_dir, data_regression):
    discoverer = JMLR()

    papers = sorted(
        discoverer.query(volume="v24", name="Yoshua Bengio", cache=cache_dir),
        key=lambda x: x.title,
    )

    data_regression.check(sort_keys(serialize(list[Paper], papers[:5])))
