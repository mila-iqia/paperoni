import pytest
from pytest_regressions.data_regression import DataRegressionFixture

from paperoni.discovery.openalex import WORK_TYPES, OpenAlex, QueryError
from paperoni.model import Focus, Focuses, PaperInfo

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
async def test_query(
    data_regression: DataRegressionFixture, query_params: dict[str, str]
):
    discoverer = OpenAlex()

    papers: list[PaperInfo] = sorted(
        [
            p
            async for p in discoverer.query(
                **query_params,
                page=1,
                per_page=100,
                limit=10000,
            )
        ],
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
                            [
                                pp
                                async for pp in discoverer.query(
                                    author="Yoshua Bengio",
                                    page=1,
                                    per_page=100,
                                    limit=100,
                                )
                            ],
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
async def test_query_error(query_params):
    discoverer = OpenAlex()
    with pytest.raises(QueryError):
        await anext(discoverer.query(**query_params))


async def test_query_limit_ignored_when_focuses_provided(capsys: pytest.CaptureFixture):
    discoverer = OpenAlex()
    results = [
        p
        async for p in discoverer.query(
            institution="mila",
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
            page=1,
            per_page=10,
            limit=1,
            work_types=WORK_TYPES,
        )
    ]

    assert len(results) == 10
    assert (
        "The 'limit' parameter is ignored when 'focuses' are provided."
        in capsys.readouterr().err.splitlines()
    )


async def test_focuses_drive_discovery_false():
    """Test that focuses with drive_discovery=False are skipped."""
    discoverer = OpenAlex()

    # This should return no results because the focus is skipped
    results = [
        p
        async for p in discoverer.query(
            institution="mila",
            focuses=Focuses([Focus(type="author", name="Yoshua Bengio", score=1.0)]),
            page=1,
            per_page=10,
            work_types=WORK_TYPES,
        )
    ]
    assert len(results) == 0


@pytest.mark.parametrize(
    ["query_params", "focused_params"],
    [
        [
            {
                "author": "Yoshua Bengio",
                "institution": "mila",
            },
            {
                "author": "Unknown Author",  # Focuses should take precedence over other parameters
                "institution": "mila",
                "focuses": {
                    "type": "author",
                    "name": "Yoshua Bengio",
                },
            },
        ],
        [
            {
                "author_id": "a5086198262",
                "institution": "mila",
            },
            {
                "author_id": "aINVALID",  # Focuses should take precedence over other parameters
                "institution": "mila",
                "focuses": {
                    "type": "author_openalex",
                    "name": "a5086198262",
                },
            },
        ],
        [
            {
                "institution": "mila",
            },
            {
                "focuses": {
                    "type": "institution",
                    "name": "mila",
                },
            },
        ],
    ],
)
async def test_focuses(query_params, focused_params):
    """Test that focuses."""
    discoverer = OpenAlex()

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
    direct_results = [
        p
        async for p in discoverer.query(
            **query_params, page=1, per_page=10, limit=100, work_types=WORK_TYPES
        )
    ]

    focus_results = [
        p
        async for p in discoverer.query(
            **focused_params,
            focuses=focuses,
            page=1,
            per_page=10,
            work_types=WORK_TYPES,
        )
    ]

    # Both should return the same papers
    direct_papers = [p.paper.title for p in direct_results]
    focus_papers = [p.paper.title for p in focus_results]

    assert focus_papers == direct_papers
    assert len(focus_results) == 10

    # All focus results should have the rescored score
    for result in focus_results:
        assert result.score == 10.0


async def test_focuses_multiple_focuses():
    """Test multiple focuses with different types."""
    discoverer = OpenAlex()

    focuses = Focuses(
        [
            Focus(type="author", name="Yoshua Bengio", score=1.0, drive_discovery=True),
            Focus(type="institution", name="mila", score=2.0, drive_discovery=True),
            Focus(type="author", name="Yoshua Bengio", score=1.0, drive_discovery=True),
            Focus(type="author", name="Unknown Author", score=0.5),  # Should be skipped
        ]
    )

    results = [
        p
        async for p in discoverer.query(
            focuses=focuses, page=1, per_page=10, work_types=WORK_TYPES
        )
    ]

    # Should get results from both author and institution queries
    assert len(results) == 30

    # The last active focus is a duplicate of the first focus, so the first 10
    # results should be the same as the last 10 results
    assert [p.paper.title for p in results][:10] == [p.paper.title for p in results][20:]
