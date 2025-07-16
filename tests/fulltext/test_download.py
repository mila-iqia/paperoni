import os

from pytest_regressions.file_regression import FileRegressionFixture

from paperoni import config
from paperoni.discovery.openreview import OpenReviewDispatch
from paperoni.fulltext import download


def test_download_link_priority(file_regression: FileRegressionFixture):
    openreview_dispatch: OpenReviewDispatch = config.discoverers["openreview"]
    paper = next(
        openreview_dispatch.query(
            venue="NeurIPS.cc/2024/Conference",
            title="Improved off-policy training of diffusion samplers",
            block_size=1,
            limit=1,
        )
    )

    assert (
        len(
            list(
                download.fulltext(paper, cache_policy=download.CachePolicies.NO_DOWNLOAD)
            )
        )
        == 0
    )

    files_stat: list[os.stat_result] = []
    for fulltext in download.fulltext(paper):
        files_stat.append(fulltext.stat())
        assert files_stat[-1].st_size
        metadata = fulltext.with_name("meta.yaml")
        file_regression.check(metadata.read_text(), basename=metadata.parent.name)

    assert files_stat == [
        fulltext.stat()
        for fulltext in download.fulltext(paper, cache_policy=download.CachePolicies.USE)
    ]
    assert files_stat == [
        fulltext.stat()
        for fulltext in download.fulltext(
            paper, cache_policy=download.CachePolicies.NO_DOWNLOAD
        )
    ]

    force_files_stat = [
        fulltext.stat()
        for fulltext in download.fulltext(
            paper, cache_policy=download.CachePolicies.FORCE
        )
    ]
    assert len(force_files_stat) == len(files_stat)
    assert [st.st_ctime for st in files_stat] != [st.st_ctime for st in force_files_stat]
