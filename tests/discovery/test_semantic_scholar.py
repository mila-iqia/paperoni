from itertools import permutations

import pytest
from pytest_regressions.file_regression import FileRegressionFixture

from paperoni.discovery.base import PaperInfo
from paperoni.discovery.semantic_scholar import SemanticScholar
from paperoni.model.classes import Paper

from ..utils import check_papers, split_on


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
def test_query(file_regression: FileRegressionFixture, query_params: dict[str, str]):
    discoverer = SemanticScholar()

    papers: list[PaperInfo] = sorted(
        discoverer.query(**query_params, block_size=100),
        key=lambda x: x.paper.title,
    )

    assert papers, f"No papers found for {query_params=}"

    match next(iter(query_params.keys())):
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
                [
                    author
                    for author in paper.paper.authors
                    if any(
                        name_variant.lower() in author.author.name.lower()
                        for name_variant in name_variants
                    )
                ]
                for paper in papers
            ), f"Some papers do not contain the author {query_params['author']=}"
        case "title":
            assert all(
                # Search on title will return a match for each word in the query
                set(split_on(query_params["title"].lower()))
                & set(split_on(paper.paper.title.lower()))
                for paper in papers
            ), f"Some papers' titles do not contain the words {query_params['title']=}"
        case _:
            assert False, f"Unknown query parameter: {query_params=}"

    check_papers(file_regression, papers)
