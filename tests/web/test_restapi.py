from datetime import date
from unittest.mock import patch

import httpx
import pytest
from pytest_regressions.data_regression import DataRegressionFixture

from paperoni.model.classes import (
    DatePrecision,
    Institution,
    Link,
    Paper,
    PaperAuthor,
    Release,
    Venue,
    VenueType,
)


@pytest.fixture(scope="session")
def mock_papers():
    """Create mock papers for testing."""
    yield [
        Paper(
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
        Paper(
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
        Paper(
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
        ({"offset": 0, "size": 2}, 2, 2, 3),
        ({"offset": 2, "size": 2}, 1, None, 3),
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
