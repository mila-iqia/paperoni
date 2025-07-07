import pytest
from pytest_regressions.file_regression import FileRegressionFixture

from paperoni.discovery import openreview
from paperoni.discovery.openreview import OpenReview, OpenReviewDispatch
from paperoni.model.classes import Paper

from ..utils import check_papers, iter_links_ids, iter_releases


@pytest.mark.parametrize(
    "query_params",
    [
        {"venue": "NeurIPS.cc/2020/Conference"},
        {"venue": "NeurIPS.cc/2024/Conference"},
        {"paper_id": "gVTkMsaaGI", "venue": "NeurIPS.cc/2024/Conference"},
        {"author": "Yoshua Bengio", "venue": "NeurIPS.cc/2024/Conference"},
        {"author_id": "~Yoshua_Bengio1", "venue": "NeurIPS.cc/2024/Conference"},
        # TODO: Fix this test. Querying by title returns no results.
        # {
        #     "title": "Amortizing intractable inference in diffusion models for vision, language, and control",
        #     "venue": "NeurIPS.cc/2024/Conference",
        # },
    ],
)
def test_query(file_regression: FileRegressionFixture, query_params: dict[str, str]):
    query_params = {**query_params, "block_size": 100, "limit": 1000}
    api_versions = [1, 2]

    papers_per_version: dict[int, list[Paper]] = {}
    for api_version in api_versions:
        discoverer = OpenReview(api_version)

        try:
            papers_per_version[api_version] = sorted(
                discoverer.query(**query_params),
                key=lambda x: x.title,
            )
        except openreview.openreview.OpenReviewException:
            papers_per_version[api_version] = []

    if papers_per_version[1] and papers_per_version[2]:
        assert (
            False
        ), f"The same papers are not expected to be in version 1 and 2 at the same time. Papers: {len(papers_per_version[1])=} {len(papers_per_version[2])=}"

    papers: list[Paper] = sum(papers_per_version.values(), [])

    assert papers, f"No papers found for {query_params=}"

    assert papers == sorted(
        OpenReviewDispatch(api_versions=api_versions).query(**query_params),
        key=lambda x: x.title,
    ), f"Querying with OpenReview({api_versions=}) should return the same papers as querying with OpenReviewDispatch"

    match next(iter(query_params.keys())):
        case "venue":
            assert all(
                [
                    rel
                    for rel in iter_releases(paper)
                    if query_params["venue"].lower() == rel.venue.name.lower()
                ]
                for paper in papers
            ), f"No paper found for {query_params['institution']=}"
        case "paper_id":
            assert all(
                [
                    link_id
                    for link_id in iter_links_ids(paper)
                    if query_params["paper_id"] == link_id
                ]
                for paper in papers
            ), f"No paper found for {query_params['institution']=}"
        case "author":
            assert all(
                [
                    author
                    for author in paper.authors
                    if query_params["author"].lower() in author.author.name.lower()
                ]
                for paper in papers
            ), f"No paper found for {query_params['author']=}"
        case "author_id":
            assert papers == sorted(
                discoverer.query(
                    author="Yoshua Bengio",
                    venue=query_params["venue"],
                    block_size=100,
                    limit=100,
                ),
                key=lambda x: x.title,
            ), f"Querying by author ID should return the same papers as querying by author name"
        case "title":
            assert all(
                query_params["title"].lower() == paper.title.lower() for paper in papers
            ), f"No paper found for {query_params['title']=}"
        case _:
            assert False, f"Unknown query parameter: {query_params=}"

    check_papers(file_regression, papers)
