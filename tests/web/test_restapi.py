from dataclasses import replace
from datetime import date

import httpx
import pytest
from pytest_regressions.data_regression import DataRegressionFixture
from serieux import serialize

from paperoni.model.classes import (
    Author,
    CollectionPaper,
    DatePrecision,
    Institution,
    PaperAuthor,
    Release,
    Venue,
    VenueType,
)


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
        {"title": "Firmness Testing Protocols"},
        {"author": "Anna Banana"},
        {"institution": "Fruit Research Institute"},
        {
            "title": "Firmness Testing Protocols",
            "author": "Milo Meloni",
            "institution": "Global Fruit Standards Organization",
        },
    ],
)
def test_search_endpoint(data_regression: DataRegressionFixture, app, params):
    """Test search endpoint with valid authentication."""
    user = app.client("seeker@website.web")
    response = user.get("/api/v1/search", **params)
    assert response.status_code == 200
    data_regression.check(response.json())


@pytest.mark.parametrize(
    ["params", "count", "next_offset", "total"],
    [
        ({}, 10, None, 10),
        ({"offset": 0, "limit": 2}, 2, 2, 10),
        ({"offset": 9, "limit": 2}, 1, None, 10),
    ],
)
def test_search_endpoint_pagination(
    data_regression: DataRegressionFixture,
    app,
    params,
    count,
    next_offset,
    total,
):
    """Test search endpoint pagination."""
    user = app.client("seeker@website.web")
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
):
    """Test that search respects max_results limit."""
    with app_factory({"paperoni.server.max_results": 2}) as app:
        user = app.client("seeker@website.web")
        response = user.get("/api/v1/search", size=100)
        assert response.status_code == 200
        data = response.json()
        # The size should be limited to max_results
        assert data["count"] == 2
        assert data["total"] == 10
        assert data["next_offset"] == 2
        assert len(data["results"]) == 2

        data_regression.check(data["results"])


def test_search_endpoint_empty_results(app):
    """Test search endpoint with empty results."""
    user = app.client("seeker@website.web")

    response = user.get("/api/v1/search", author="no existo")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["total"] == 0
    assert data["results"] == []
    assert data["next_offset"] is None


def test_get_paper_endpoint(app):
    """Test get paper by ID endpoint."""
    user = app.client("seeker@website.web")

    response = user.get("/api/v1/paper/3")
    assert response.status_code == 200
    data = response.json()
    assert (
        data["title"]
        == "Acoustic Resonance Methods for Internal Defect Detection in Watermelons"
    )
    assert data["id"] == 3


def test_get_paper_endpoint_not_found(app):
    """Test get paper by ID endpoint returns 404 when paper not found."""
    user = app.client("seeker@website.web")
    response = user.get("/api/v1/paper/999", expect=404)
    assert response.status_code == 404
    assert "Paper with ID 999 not found" in response.json()["detail"]


def test_get_paper_requires_authentication(app):
    """Test that the get paper endpoint requires authentication."""
    response = httpx.get(f"{app}/api/v1/paper/123")
    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]


@pytest.fixture
def edited_paper():
    yield CollectionPaper(
        id=3,
        title="Acoustic Resonance Methods for Internal Defect Detection in Cantaloupes",
        abstract="A portable acoustic testing device is developed and validated for detecting hollow heart and internal cracks in cantaloupes with 89% sensitivity.",
        authors=[
            PaperAuthor(
                display_name="Milo Meloni",
                author=Author(name="Milo Meloni"),
                affiliations=[Institution(name="Huge University", category="academia")],
            ),
        ],
        releases=[
            Release(
                venue=Venue(
                    type=VenueType.conference,
                    name="European Symposium on Fruit Testing",
                    series="ESFT",
                    date=date(2023, 6, 5),
                    date_precision=DatePrecision.day,
                ),
                status="published",
            )
        ],
    )


def test_edit_paper_endpoint(wr_app, edited_paper):
    """Test edit paper endpoint."""
    admin = wr_app.client("admin@website.web")

    original = admin.get("/api/v1/paper/3").json()
    assert "Watermelon" in original["title"]
    assert "Cantaloupe" not in original["title"]
    assert len(original["authors"]) == 2

    response = admin.post(
        "/api/v1/edit",
        paper=serialize(CollectionPaper, edited_paper),
    )

    assert response.status_code == 200

    modified = admin.get("/api/v1/paper/3").json()
    assert "Watermelon" not in modified["title"]
    assert "Cantaloupe" in modified["title"]
    assert len(modified["authors"]) == 1


def test_edit_paper_endpoint_not_found(wr_app, edited_paper):
    """Test edit paper endpoint returns error when paper not found."""
    admin = wr_app.client("admin@website.web")
    edited_paper = replace(edited_paper, id=999)
    response = admin.post(
        "/api/v1/edit",
        paper=serialize(CollectionPaper, edited_paper),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "Paper with ID 999 not found" in data["message"]
    assert data["paper"] is None


def test_edit_paper_endpoint_no_id(wr_app, edited_paper):
    """Test edit paper endpoint returns error when paper has no ID."""
    admin = wr_app.client("admin@website.web")
    edited_paper = replace(edited_paper, id=None)

    response = admin.post(
        "/api/v1/edit",
        paper=serialize(CollectionPaper, edited_paper),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "Paper must have an ID to be edited" in data["message"]
    assert data["paper"] is None


def test_edit_paper_requires_validate_authentication(wr_app, edited_paper):
    """Test that the edit paper endpoint requires validate authentication."""
    # Test with no authentication
    unlogged = wr_app.client()
    response = unlogged.post(
        "/api/v1/edit",
        paper=serialize(CollectionPaper, edited_paper),
        expect=401,
    )
    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]

    # Test with user without validate capability
    user = wr_app.client("seeker@website.web")
    response = user.post(
        "/api/v1/edit",
        paper=serialize(CollectionPaper, edited_paper),
        expect=403,
    )
    assert response.status_code == 403
    assert "validate capability required" in response.json()["detail"]
