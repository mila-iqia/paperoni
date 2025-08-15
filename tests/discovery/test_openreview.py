import pytest
from pytest_regressions.data_regression import DataRegressionFixture

from paperoni.discovery import openreview
from paperoni.discovery.openreview import OpenReview, OpenReviewDispatch
from paperoni.model import PaperInfo
from paperoni.model.focus import Focus, Focuses

from ..utils import check_papers, iter_links_ids, iter_releases


@pytest.mark.parametrize(
    "query_params",
    [
        {"venue": "NeurIPS.cc/2020/Conference"},
        {"venue": "NeurIPS.cc/2024/Conference"},
        {"paper_id": "gVTkMsaaGI"},
        {"author": "Yoshua Bengio", "venue": "NeurIPS.cc/2024/Conference"},
        {"author_id": "~Yoshua_Bengio1", "venue": "NeurIPS.cc/2024/Conference"},
        {
            "venue": "NeurIPS.cc/2024/Conference",
            "title": "Improved off-policy training of diffusion samplers",
        },
    ],
)
def test_query(data_regression: DataRegressionFixture, query_params: dict[str, str]):
    query_params = {**query_params, "block_size": 100, "limit": 1000}
    openreview_dispatch: OpenReviewDispatch = OpenReviewDispatch()
    api_versions: list[int] = openreview_dispatch.api_versions

    papers_per_version: dict[int, list[PaperInfo]] = {}
    for api_version in api_versions:
        discoverer = OpenReview(api_version)

        try:
            papers_per_version[api_version] = sorted(
                discoverer.query(**query_params),
                key=lambda x: x.paper.title,
            )
        except openreview.openreview.OpenReviewException:
            papers_per_version[api_version] = []

    if papers_per_version[1] and papers_per_version[2]:
        assert (
            False
        ), f"The same papers are not expected to be in version 1 and 2 at the same time. Papers: {len(papers_per_version[1])=} {len(papers_per_version[2])=}"

    papers: list[PaperInfo] = sum(papers_per_version.values(), [])

    assert papers, f"No papers found for {query_params=}"

    assert [p.paper for p in papers] == [
        p.paper
        for p in sorted(
            openreview_dispatch.query(**query_params),
            key=lambda x: x.paper.title,
        )
    ], f"Querying with OpenReview({api_versions=}) should return the same papers as querying with OpenReviewDispatch"

    match_found = False

    for param in query_params:
        match param:
            case "venue":
                assert all(
                    any(
                        query_params["venue"].lower() == rel.venue.name.lower()
                        for rel in iter_releases(paper.paper)
                    )
                    for paper in papers
                ), f"Some papers do not contain the venue {query_params['venue']=}"
                match_found = True

            case "paper_id":
                assert all(
                    any(
                        query_params["paper_id"] == link_id
                        for link_id in iter_links_ids(paper.paper)
                    )
                    for paper in papers
                ), f"Some papers do not contain the paper ID {query_params['paper_id']=}"
                match_found = True

            case "author":
                assert all(
                    any(
                        query_params["author"].lower() in author.author.name.lower()
                        for author in paper.paper.authors
                    )
                    for paper in papers
                ), f"Some papers do not contain the author {query_params['author']=}"
                match_found = True

            case "author_id":
                assert [p.paper for p in papers] == [
                    p.paper
                    for p in sorted(
                        openreview_dispatch.query(
                            author="Yoshua Bengio",
                            venue=query_params["venue"],
                            block_size=100,
                            limit=100,
                        ),
                        key=lambda x: x.paper.title,
                    )
                ], "Querying by author ID, at least for Yoshua Bengio, should return the same papers as querying by author name"
                match_found = True

            case "title":
                assert all(
                    query_params["title"].lower() == paper.paper.title.lower()
                    for paper in papers
                ), f"Some papers' titles do not contain the words {query_params['title']=}"
                match_found = True

    if not match_found:
        assert False, f"Unknown query parameters: {query_params=}"

    check_papers(data_regression, papers)


def test_query_limit_ignored_when_focuses_provided(capsys: pytest.CaptureFixture):
    discoverer = OpenReviewDispatch()
    results = list(
        discoverer.query(
            focuses=Focuses(
                [
                    Focus(
                        type="author_openreview",
                        name="~Yoshua_Bengio1",
                        score=1.0,
                        drive_discovery=True,
                    )
                ]
            ),
            limit=1,
        )
    )

    assert (
        len(results) > 1
    )  # As limit is ignored, up to default limit (currently 10000) matching results are returned
    assert (
        "The 'limit' parameter is ignored when 'focuses' are provided."
        in capsys.readouterr().err.splitlines()
    )


def test_focuses_drive_discovery_false():
    """Test that focuses with drive_discovery=False are skipped."""
    discoverer = OpenReviewDispatch()

    # This should return no results because the focus is skipped
    results = list(
        discoverer.query(
            venue="NeurIPS.cc/2024/Conference",
            focuses=Focuses([Focus(type="author", name="Yoshua Bengio", score=1.0)]),
        )
    )
    assert len(results) == 0


@pytest.mark.parametrize(
    ["query_params", "focused_params"],
    [
        [
            {
                "author_id": "~Yoshua_Bengio1",
            },
            {
                "author_id": "~INVALID",  # Focuses should take precedence over other parameters
                "focuses": {
                    "type": "author_openreview",
                    "name": "~Yoshua_Bengio1",
                },
            },
        ],
    ],
)
def test_focuses(query_params, focused_params):
    """Test that focuses."""
    discoverer = OpenReviewDispatch()

    focuses = Focuses(
        [
            Focus(
                **focused_params.pop("focuses"),
                score=10.0,
                drive_discovery=True,
            )
        ]
    )

    # Query with focuses should return the same results as direct author query
    direct_results = list(discoverer.query(**query_params))

    focus_results = list(discoverer.query(**focused_params, focuses=focuses))

    # Both should return the same papers
    direct_papers = [p.paper.title for p in direct_results]
    focus_papers = [p.paper.title for p in focus_results]

    assert focus_papers == direct_papers

    # All focus results should have the rescored score
    for result in focus_results:
        assert result.score == 10.0
