import pytest
from pytest_regressions.data_regression import DataRegressionFixture

from paperoni.discovery.base import PaperInfo
from paperoni.discovery.openalex import OpenAlex, QueryError

from ..utils import check_papers, filter_test_papers, iter_affiliations, split_on

PAPERS = [
    "A Hierarchical Latent Variable Encoder-Decoder Model for Generating Dialogues",
    "A closer look at memorization in deep networks",
    "Binarized Neural Networks",
    "Building End-To-End Dialogue Systems Using Generative Hierarchical Neural Network Models",
    "Contractive Auto-Encoders: Explicit Invariance During Feature Extraction",
    "Attention Is All You Need In Speech Separation",
    "ECAPA-TDNN Embeddings for Speaker Diarization",
    "GraphMix: Improved Training of GNNs for Semi-Supervised Learning",
    "HiFormer: Hierarchical Multi-scale Representations Using Transformers for Medical Image Segmentation",
    "Large-Scale Contrastive Language-Audio Pretraining with Feature Fusion and Keyword-to-Caption Augmentation",
]


@pytest.mark.parametrize(
    "query_params",
    [
        {"institution": "mila"},
        {"author": "Yoshua Bengio"},
        {"author_id": "a5086198262"},
        {"title": "Hierarchical Latent Variable"},
    ],
)
def test_query(data_regression: DataRegressionFixture, query_params: dict[str, str]):
    discoverer = OpenAlex()

    papers: list[PaperInfo] = sorted(
        discoverer.query(
            **query_params,
            page=1,
            per_page=100,
            limit=10000,
        ),
        key=lambda x: x.paper.title,
    )

    papers = list(filter_test_papers(papers, PAPERS))

    assert papers, f"No papers found for {query_params=}"

    match_found = False

    for param in query_params:
        match param:
            case "institution":
                assert all(
                    any(
                        query_params["institution"].lower() in aff.name.lower()
                        for aff in iter_affiliations(paper.paper)
                    )
                    for paper in papers
                ), (
                    f"Some papers do not contain the institution {query_params['institution']=}"
                )
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
                        filter_test_papers(
                            discoverer.query(
                                author="Yoshua Bengio", page=1, per_page=100, limit=100
                            ),
                            PAPERS,
                        ),
                        key=lambda x: x.paper.title,
                    )
                ], (
                    "Querying by author ID should return the same papers as querying by author name"
                )
                match_found = True

            case "title":
                # Search on title will return a match for each word in the query
                assert all(
                    set(split_on(query_params["title"].lower()))
                    & set(split_on(paper.paper.title.lower()))
                    for paper in papers
                ), (
                    f"Some papers' titles do not contain the words {query_params['title']=}"
                )
                match_found = True

    if not match_found:
        assert False, f"Unknown query parameters: {query_params=}"

    check_papers(data_regression, papers)


@pytest.mark.parametrize(
    "query_params",
    [
        {
            "author": "Yoshua Bengio",
            "author_id": "a5086198262",
        },
        {"page": 0, "per_page": 1},
        {"page": None, "per_page": 1},
        {"page": 1, "per_page": 0},
        {"page": 1, "per_page": 201},
        {"page": 1, "per_page": None},
    ],
)
def test_query_error(query_params):
    discoverer = OpenAlex()
    with pytest.raises(QueryError):
        next(discoverer.query(**query_params))
