from itertools import permutations

import pytest
from pytest_regressions.data_regression import DataRegressionFixture

from paperoni.discovery.semantic_scholar import SemanticScholar
from paperoni.model import PaperInfo
from paperoni.model.focus import Focus, Focuses

from ..utils import check_papers, filter_test_papers, split_on

PAPERS = [
    "A Two-Stream Continual Learning System With Variational Domain-Agnostic Feature Replay",
    "A community effort in SARS-CoV-2 drug discovery",
    "A hybrid coder for hidden Markov models using a recurrent neural networks",
    "A neuronal least-action principle for real-time learning in cortical circuits",
    "AI and Catastrophic Risk",
    "A Hierarchical Latent Variable Model for Data Visualization",
    "A Structured Latent Variable Recurrent Network With Stochastic Attention For Generating Weibo Comments",
    "A hierarchical model of cognitive flexibility in children: Extending the relationship...ility, creativity and academic achievement",
    "Bayesian Variable Selection for Pareto Regression Models with Latent Multivariate Log...ith Applications to Earthquake Magnitudes.",
    "Bayesian latent variable models for hierarchical clustered count outcomes with repeated measures in microbiome studies",
]


@pytest.mark.parametrize(
    "query_params",
    [
        {"author": "Yoshua Bengio", "limit": 1000},
        {
            "title": "Hierarchical Latent Variable",
            # For more than 100 papers, semantic scholar starts returning unrelated results.
            "limit": 100,
        },
    ],
)
def test_query(data_regression: DataRegressionFixture, query_params: dict[str, str]):
    discoverer = SemanticScholar()

    papers: list[PaperInfo] = sorted(
        discoverer.query(**query_params, block_size=100),
        key=lambda x: x.paper.title,
    )

    papers = list(filter_test_papers(papers, PAPERS))

    assert papers, f"No papers found for {query_params=}"

    match_found = False

    for param in query_params:
        match param:
            case "author":
                name_splits = [part.strip() for part in query_params["author"].split()]

                # Generate all permutations of name parts
                all_permutations = list(permutations(name_splits))

                name_variants = []

                # For each permutation, add the original and abbreviated versions
                for perm in all_permutations:
                    perm_list = list(perm)
                    # Add the original permutation
                    name_variants.append(perm_list)
                    # Add abbreviated versions of this permutation
                    for i in range(len(perm_list)):
                        abbreviated = (
                            perm_list[:i] + [f"{perm_list[i][0]}."] + perm_list[i + 1 :]
                        )
                        name_variants.append(abbreviated)

                name_variants = [" ".join(variant) for variant in name_variants]

                assert all(
                    any(
                        any(
                            name_variant.lower() in author.author.name.lower()
                            for name_variant in name_variants
                        )
                        for author in paper.paper.authors
                    )
                    for paper in papers
                ), f"Some papers do not contain the author {query_params['author']=}"
                match_found = True

            case "title":
                assert all(
                    # Search on title will return a match for each word in the query
                    set(split_on(query_params["title"].lower()))
                    & set(split_on(paper.paper.title.lower()))
                    for paper in papers
                ), (
                    f"Some papers' titles do not contain the words {query_params['title']=}"
                )
                match_found = True

    if not match_found:
        assert False, f"Unknown query parameter: {query_params=}"

    check_papers(data_regression, papers)


def test_query_limit_ignored_when_focuses_provided(capsys: pytest.CaptureFixture):
    discoverer = SemanticScholar()
    results = list(
        discoverer.query(
            author="Yoshua Bengio",
            focuses=Focuses(
                [
                    Focus(
                        type="author",
                        name="Yoshua Bengio",
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
    )  # As limit is ignored, up to default limit (currently 1000) matching results are returned
    assert (
        "The 'limit' parameter is ignored when 'focuses' are provided."
        in capsys.readouterr().err.splitlines()
    )


def test_focuses_drive_discovery_false():
    """Test that focuses with drive_discovery=False are skipped."""
    discoverer = SemanticScholar()

    # This should return no results because the focus is skipped
    results = list(
        discoverer.query(
            focuses=Focuses([Focus(type="author", name="Yoshua Bengio", score=1.0)]),
        )
    )
    assert len(results) == 0


@pytest.mark.parametrize(
    ["query_params", "focused_params"],
    [
        [
            {
                "author": "Yoshua Bengio",
            },
            {
                "author": "Unknown Author",  # Focuses should take precedence over other parameters
                "focuses": {
                    "type": "author",
                    "name": "Yoshua Bengio",
                },
            },
        ],
    ],
)
def test_focuses(query_params, focused_params):
    """Test that focuses."""
    discoverer = SemanticScholar()

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
