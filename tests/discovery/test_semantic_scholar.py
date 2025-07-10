from itertools import permutations

import pytest
from pytest_regressions.data_regression import DataRegressionFixture

from paperoni.discovery.semantic_scholar import SemanticScholar
from paperoni.model import PaperInfo

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
