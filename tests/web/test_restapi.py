from datetime import date
from unittest.mock import patch

import httpx
import pytest
from pytest_regressions.data_regression import DataRegressionFixture
from serieux import serialize

from paperoni.model.classes import (
    Author,
    CollectionPaper,
    DatePrecision,
    Institution,
    Link,
    PaperAuthor,
    Release,
    Venue,
    VenueType,
)


@pytest.fixture(scope="session")
def mock_papers():
    """Create mock papers for testing."""
    yield [
        CollectionPaper(
            id=1,
            title="Test Paper 1",
            abstract="This is a test paper",
            authors=[
                PaperAuthor(
                    display_name="John Doe",
                    author=None,
                    affiliations=[Institution(name="MIT", category=None)],
                )
            ],
            releases=[
                Release(
                    venue=Venue(
                        name="Test Conference",
                        type=VenueType.conference,
                        series="Test Conference",
                        date=date(2023, 1, 1),
                        date_precision=DatePrecision.day,
                    ),
                    status="published",
                )
            ],
            links=[Link(type="doi", link="10.1000/test1")],
        ),
        CollectionPaper(
            id=2,
            title="Test Paper 2",
            abstract="This is another test paper",
            authors=[
                PaperAuthor(
                    display_name="Jane Smith",
                    author=None,
                    affiliations=[Institution(name="Stanford", category=None)],
                )
            ],
            releases=[
                Release(
                    venue=Venue(
                        name="Test Journal",
                        type=VenueType.journal,
                        series="Test Journal",
                        date=date(2023, 2, 1),
                        date_precision=DatePrecision.day,
                    ),
                    status="published",
                )
            ],
            links=[Link(type="doi", link="10.1000/test2")],
        ),
        CollectionPaper(
            id=3,
            title="Machine Learning Paper",
            abstract="A paper about machine learning",
            authors=[
                PaperAuthor(
                    display_name="Alice Johnson",
                    author=None,
                    affiliations=[Institution(name="MIT", category=None)],
                )
            ],
            releases=[
                Release(
                    venue=Venue(
                        name="ML Conference",
                        type=VenueType.conference,
                        series="ML Conference",
                        date=date(2023, 3, 1),
                        date_precision=DatePrecision.day,
                    ),
                    status="published",
                )
            ],
            links=[Link(type="doi", link="10.1000/ml1")],
        ),
    ]


@pytest.mark.parametrize(
    "endpoint,expected",
    [
        ("/api/v1/search", 200),
        ("/api/v1/fulltext/locate", 422),
        ("/api/v1/fulltext/download", 422),
    ],
)
def test_get_endpoint_requires_user_authentication(
    app,
    endpoint,
    expected,
):
    """Test that the GET endpoints require authentication."""
    response = httpx.get(f"{app}{endpoint}")
    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]

    headers = {"Authorization": "Bearer invalid-token"}
    response = httpx.get(f"{app}{endpoint}", headers=headers)

    assert response.status_code == 401
    assert "Malformed authorization" in response.json()["detail"]

    user = app.client("admin@website.web")

    response = user.get(endpoint, expect=expected)


@pytest.mark.parametrize("endpoint", ["/api/v1/focus/auto"])
def test_endpoint_requires_admin_authentication(app, endpoint):
    """Test that the admin GET endpoints require admin authentication."""

    unlogged = app.client()
    response = unlogged.get(endpoint, expect=401)
    assert "Authentication required" in response.json()["detail"]

    user = app.client("seeker@website.web")
    response = user.get(endpoint, expect=403)
    assert "admin capability required" in response.json()["detail"]

    admin = app.client("admin@website.web")
    response = admin.get(endpoint)


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"title": "Machine Learning"},
        {"author": "John Doe"},
        {"institution": "MIT"},
        {"title": "Machine Learning", "author": "John Doe", "institution": "MIT"},
    ],
)
def test_search_endpoint(
    data_regression: DataRegressionFixture,
    app,
    mock_papers,
    params,
):
    """Test search endpoint with valid authentication."""
    user = app.client("seeker@website.web")

    with patch("paperoni.web.restapi._search") as mock_search:
        mock_search.return_value = (mock_papers, 3, None, 3)

        response = user.get("/api/v1/search", **params)

    assert response.status_code == 200
    assert mock_search.call_count == 1

    data_regression.check(mock_search.call_args.args)


@pytest.mark.parametrize(
    ["params", "count", "next_offset", "total"],
    [
        ({}, 3, None, 3),
        ({"offset": 0, "limit": 2}, 2, 2, 3),
        ({"offset": 2, "limit": 2}, 1, None, 3),
    ],
)
def test_search_endpoint_pagination(
    data_regression: DataRegressionFixture,
    app,
    mock_papers,
    params,
    count,
    next_offset,
    total,
):
    """Test search endpoint pagination."""
    user = app.client("seeker@website.web")

    with patch("paperoni.web.restapi.SearchRequest.run") as mock_run:
        mock_run.return_value = mock_papers

        response = user.get("/api/v1/search", **params)

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == count
    assert data["next_offset"] == next_offset
    assert data["total"] == total

    data_regression.check(data["results"])


def test_search_endpoint_max_results_limit(
    data_regression: DataRegressionFixture,
    app_factory,
    mock_papers,
):
    """Test that search respects max_results limit."""
    with app_factory({"paperoni.server.max_results": 2}) as app:
        user = app.client("seeker@website.web")
        with patch("paperoni.web.restapi.SearchRequest.run") as mock_run:
            mock_run.return_value = mock_papers

            # Request more than max_results
            response = user.get("/api/v1/search", size=100)

        assert response.status_code == 200
        data = response.json()
        # The size should be limited to max_results
        assert data["count"] == 2
        assert data["total"] == 3
        assert data["next_offset"] == 2
        assert len(data["results"]) == 2

        data_regression.check(data["results"])


def test_search_endpoint_empty_results(app):
    """Test search endpoint with empty results."""
    user = app.client("seeker@website.web")

    with patch("paperoni.web.restapi.SearchRequest.run") as mock_run:
        mock_run.return_value = []

        response = user.get("/api/v1/search")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["total"] == 0
        assert data["results"] == []
        assert data["next_offset"] is None


def test_get_paper_endpoint(app, mock_papers):
    """Test get paper by ID endpoint."""
    user = app.client("seeker@website.web")

    with patch("paperoni.web.restapi.Coll") as mock_coll:
        # Create a mock collection paper with an ID
        from paperoni.model.classes import CollectionPaper

        mock_paper = CollectionPaper(**mock_papers[0].__dict__)
        mock_paper.id = 123

        mock_coll.return_value.collection.find_by_id.return_value = mock_paper

        response = user.get("/api/v1/paper/123")

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Paper 1"
        assert data["id"] == 123


def test_get_paper_endpoint_not_found(app):
    """Test get paper by ID endpoint returns 404 when paper not found."""
    user = app.client("seeker@website.web")

    with patch("paperoni.web.restapi.Coll") as mock_coll:
        mock_coll.return_value.collection.find_by_id.return_value = None

        response = user.get("/api/v1/paper/999", expect=404)

        assert response.status_code == 404
        assert "Paper with ID 999 not found" in response.json()["detail"]


def test_get_paper_requires_authentication(app):
    """Test that the get paper endpoint requires authentication."""
    response = httpx.get(f"{app}/api/v1/paper/123")
    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]


def test_edit_paper_endpoint(app):
    """Test edit paper endpoint."""
    admin = app.client("admin@website.web")

    with patch("paperoni.web.restapi.Coll") as mock_coll:
        # Create a properly formed paper with all required fields
        original_paper = CollectionPaper(
            id=123,
            title="Test Paper 1",
            abstract="This is a test paper",
            authors=[
                PaperAuthor(
                    display_name="John Doe",
                    author=Author(name="John Doe"),
                    affiliations=[Institution(name="MIT")],
                )
            ],
            releases=[
                Release(
                    venue=Venue(
                        name="Test Conference",
                        type=VenueType.conference,
                        series="Test Conference",
                        date=date(2023, 1, 1),
                        date_precision=DatePrecision.day,
                    ),
                    status="published",
                )
            ],
            links=[Link(type="doi", link="10.1000/test1")],
        )

        # Create an edited version
        edited_paper = CollectionPaper(
            id=123,
            title="Updated Test Paper 1",
            abstract="This is an updated test paper",
            authors=[
                PaperAuthor(
                    display_name="John Doe",
                    author=Author(name="John Doe"),
                    affiliations=[Institution(name="MIT")],
                )
            ],
            releases=[
                Release(
                    venue=Venue(
                        name="Test Conference",
                        type=VenueType.conference,
                        series="Test Conference",
                        date=date(2023, 1, 1),
                        date_precision=DatePrecision.day,
                    ),
                    status="published",
                )
            ],
            links=[Link(type="doi", link="10.1000/test1")],
        )

        mock_coll.return_value.collection.find_by_id.return_value = original_paper

        response = admin.post(
            "/api/v1/edit",
            paper=serialize(CollectionPaper, edited_paper),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Paper 123 updated successfully"
        assert data["paper"]["title"] == "Updated Test Paper 1"
        assert data["paper"]["abstract"] == "This is an updated test paper"

        # Verify that edit_paper was called
        mock_coll.return_value.collection.edit_paper.assert_called_once()


def test_edit_paper_endpoint_not_found(app):
    """Test edit paper endpoint returns error when paper not found."""
    admin = app.client("admin@website.web")

    with patch("paperoni.web.restapi.Coll") as mock_coll:
        # Create a paper with an ID that doesn't exist
        paper = CollectionPaper(
            id=999,
            title="Test Paper",
            abstract="This is a test paper",
            authors=[
                PaperAuthor(
                    display_name="John Doe",
                    author=Author(name="John Doe"),
                    affiliations=[Institution(name="MIT")],
                )
            ],
            releases=[
                Release(
                    venue=Venue(
                        name="Test Conference",
                        type=VenueType.conference,
                        series="Test Conference",
                        date=date(2023, 1, 1),
                        date_precision=DatePrecision.day,
                    ),
                    status="published",
                )
            ],
            links=[Link(type="doi", link="10.1000/test1")],
        )

        mock_coll.return_value.collection.find_by_id.return_value = None

        response = admin.post(
            "/api/v1/edit",
            paper=serialize(CollectionPaper, paper),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Paper with ID 999 not found" in data["message"]
        assert data["paper"] is None


def test_edit_paper_endpoint_no_id(app):
    """Test edit paper endpoint returns error when paper has no ID."""
    admin = app.client("admin@website.web")

    paper = CollectionPaper(
        id=None,
        title="Test Paper",
        abstract="This is a test paper",
        authors=[
            PaperAuthor(
                display_name="John Doe",
                author=Author(name="John Doe"),
                affiliations=[Institution(name="MIT")],
            )
        ],
        releases=[
            Release(
                venue=Venue(
                    name="Test Conference",
                    type=VenueType.conference,
                    series="Test Conference",
                    date=date(2023, 1, 1),
                    date_precision=DatePrecision.day,
                ),
                status="published",
            )
        ],
        links=[Link(type="doi", link="10.1000/test1")],
    )

    response = admin.post(
        "/api/v1/edit",
        paper=serialize(CollectionPaper, paper),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "Paper must have an ID to be edited" in data["message"]
    assert data["paper"] is None


def test_edit_paper_requires_validate_authentication(app):
    """Test that the edit paper endpoint requires validate authentication."""
    # Create a properly formed paper
    paper = CollectionPaper(
        id=123,
        title="Test Paper",
        abstract="This is a test paper",
        authors=[
            PaperAuthor(
                display_name="John Doe",
                author=Author(name="John Doe"),
                affiliations=[Institution(name="MIT")],
            )
        ],
        releases=[
            Release(
                venue=Venue(
                    name="Test Conference",
                    type=VenueType.conference,
                    series="Test Conference",
                    date=date(2023, 1, 1),
                    date_precision=DatePrecision.day,
                ),
                status="published",
            )
        ],
        links=[Link(type="doi", link="10.1000/test1")],
    )

    # Test with no authentication
    unlogged = app.client()
    response = unlogged.post(
        "/api/v1/edit",
        paper=serialize(CollectionPaper, paper),
        expect=401,
    )
    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]

    # Test with user without validate capability
    user = app.client("seeker@website.web")
    response = user.post(
        "/api/v1/edit",
        paper=serialize(CollectionPaper, paper),
        expect=403,
    )
    assert response.status_code == 403
    assert "validate capability required" in response.json()["detail"]
