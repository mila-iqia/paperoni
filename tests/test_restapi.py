"""
Tests for the FastAPI REST API endpoints.
"""

from datetime import date, datetime, timezone
from unittest.mock import patch

import gifnoc
import pytest
from anyio import Path
from fastapi.testclient import TestClient
from jose import jwt
from pytest_regressions.data_regression import DataRegressionFixture

from paperoni.config import config
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
from paperoni.restapi import User, create_app


@pytest.fixture(scope="session")
def test_user():
    """Create a test user for authentication."""
    yield User(email="test@example.com", as_user=False)


@pytest.fixture(scope="session")
def mock_user_token(test_user):
    """Create a mock JWT token for testing."""
    payload = {
        "email": test_user.email,
        "as_user": False,
        "exp": datetime.now(timezone.utc).timestamp() + 3600,  # 1 hour from now
    }
    yield jwt.encode(payload, "test-secret-key", algorithm="HS256")


@pytest.fixture(scope="session")
def mock_admin_token(test_user: User):
    """Create a mock JWT token for testing."""
    payload = {
        "email": f"admin_{test_user.email}",
        "as_user": False,
        "exp": datetime.now(timezone.utc).timestamp() + 3600,  # 1 hour from now
    }
    yield jwt.encode(payload, "test-secret-key", algorithm="HS256")


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


@pytest.fixture()
def client(tmp_path: Path, test_user: User) -> TestClient:
    """Create a test client for the FastAPI app."""
    with gifnoc.overlay(
        {
            "paperoni.work_file": str(tmp_path / "work.yaml"),
            "paperoni.collection.$class": "paperoni.collection.memcoll:MemCollection",
            "paperoni.server.jwt_secret_key": "test-secret-key",
            "paperoni.server.admin_emails": [f"admin_{test_user.email}"],
        }
    ):
        with patch("paperoni.restapi.config.metadata") as mock_meta:
            mock_meta.focuses.file = config.work_file.parent / "focuses.yaml"
            mock_meta.focuses.file.write_text("[]")
            yield TestClient(create_app())


@pytest.mark.parametrize(
    "endpoint",
    [
        "/search",
        "/work/view",
        "/work/include",
        "/fulltext/locate",
        "/fulltext/download",
    ],
)
def test_get_endpoint_requires_user_authentication(
    client: TestClient, endpoint, mock_user_token
):
    """Test that the GET endpoints require authentication."""
    response = client.get(endpoint)
    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]

    headers = {"Authorization": "Bearer invalid-token"}
    response = client.get(endpoint, headers=headers)

    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]

    headers = {"Authorization": f"Bearer {mock_user_token}"}
    response = client.get(endpoint, headers=headers)

    assert response.status_code in [200, 422]


@pytest.mark.parametrize("endpoint", ["/work/add"])
def test_post_endpoint_requires_user_authentication(client: TestClient, endpoint):
    """Test that the search endpoint requires authentication."""
    response = client.post(endpoint, params={})
    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]

    headers = {"Authorization": "Bearer invalid-token"}
    response = client.post(endpoint, params={}, headers=headers)

    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]


@pytest.mark.parametrize("endpoint", ["/focus/auto"])
def test_endpoint_requires_admin_authentication(
    client: TestClient, endpoint, mock_user_token, mock_admin_token
):
    """Test that the admin GET endpoints require admin authentication."""
    response = client.get(endpoint)
    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]

    headers = {"Authorization": "Bearer invalid-token"}
    response = client.get(endpoint, headers=headers)

    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]

    headers = {"Authorization": f"Bearer {mock_user_token}"}
    response = client.get(endpoint, params={}, headers=headers)
    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]

    headers = {"Authorization": f"Bearer {mock_admin_token}"}
    response = client.get(endpoint, params={}, headers=headers)
    assert response.status_code == 200


@pytest.mark.parametrize(
    "params",
    [
        None,
        {"title": "Machine Learning"},
        {"author": "John Doe"},
        {"institution": "MIT"},
        {"title": "Machine Learning", "author": "John Doe", "institution": "MIT"},
    ],
)
def test_search_endpoint(
    data_regression: DataRegressionFixture,
    client: TestClient,
    mock_user_token,
    mock_papers,
    params,
):
    """Test search endpoint with valid authentication."""
    headers = {"Authorization": f"Bearer {mock_user_token}"}

    with patch("paperoni.restapi._search") as mock_search:
        mock_search.return_value = (mock_papers, 3, None, 3)

        response = client.get("/search", params=params, headers=headers)

    assert response.status_code == 200
    assert mock_search.call_count == 1

    data_regression.check(mock_search.call_args.args)


@pytest.mark.parametrize(
    ["params", "count", "next_offset", "total"],
    [
        (None, 3, None, 3),
        ({"offset": 0, "size": 2}, 2, 2, 3),
        ({"offset": 2, "size": 2}, 1, None, 3),
    ],
)
def test_search_endpoint_pagination(
    data_regression: DataRegressionFixture,
    client: TestClient,
    mock_user_token,
    mock_papers,
    params,
    count,
    next_offset,
    total,
):
    """Test search endpoint pagination."""
    headers = {"Authorization": f"Bearer {mock_user_token}"}

    with patch("paperoni.restapi.SearchRequest.run") as mock_run:
        mock_run.return_value = mock_papers

        response = client.get("/search", params=params, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == count
    assert data["next_offset"] == next_offset
    assert data["total"] == total

    data_regression.check(data["results"])


def test_search_endpoint_max_results_limit(
    data_regression: DataRegressionFixture,
    client: TestClient,
    mock_user_token,
    mock_papers,
):
    """Test that search respects max_results limit."""
    headers = {"Authorization": f"Bearer {mock_user_token}"}

    with gifnoc.overlay({"paperoni.server.max_results": 2}):
        with patch("paperoni.restapi.SearchRequest.run") as mock_run:
            mock_run.return_value = mock_papers

            # Request more than max_results
            response = client.get("/search", params={"size": 100}, headers=headers)

    assert response.status_code == 200
    data = response.json()
    # The size should be limited to max_results
    assert data["count"] == 2
    assert data["total"] == 3
    assert data["next_offset"] == 2
    assert len(data["results"]) == 2

    data_regression.check(data["results"])


def test_search_endpoint_empty_results(client: TestClient, mock_user_token):
    """Test search endpoint with empty results."""
    headers = {"Authorization": f"Bearer {mock_user_token}"}

    with patch("paperoni.restapi.SearchRequest.run") as mock_run:
        mock_run.return_value = []

        response = client.get("/search", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["total"] == 0
        assert data["results"] == []
        assert data["next_offset"] is None
