"""
Tests for the reports serving route.
"""

import pytest

from paperoni.config import config

report_content = "<html><body>Test Report</body></html>"


@pytest.fixture
def reports_dir(tmp_path):
    reports_dir = config.data_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    yield reports_dir


@pytest.fixture
def simple_report(reports_dir):
    name = "test_report.html"
    report_file = reports_dir / name
    report_file.write_text("<html><body>Test Report</body></html>")
    yield name


def test_reports_endpoint_requires_dev_capability(app, simple_report):
    """Test that the reports endpoint requires dev capability."""

    # Test unauthenticated access
    unlogged = app.client()
    response = unlogged.get(f"/reports/{simple_report}", expect=401)
    assert "Authentication required" in response.json()["detail"]

    # Test with user without dev capability
    user = app.client("seeker@website.web")
    response = user.get(f"/reports/{simple_report}", expect=403)
    assert "dev capability required" in response.json()["detail"]

    # Test with admin user (should have dev capability)
    admin = app.client("admin@website.web")
    response = admin.get(f"/reports/{simple_report}")
    assert response.status_code == 200


def test_reports_endpoint_serves_html_file(app, simple_report):
    """Test that the reports endpoint correctly serves an HTML file."""

    # Access the report as admin
    admin = app.client("admin@website.web")
    response = admin.get(f"/reports/{simple_report}")

    assert response.status_code == 200
    assert response.text == report_content


def test_reports_endpoint_serves_nested_files(app, reports_dir):
    """Test that the reports endpoint can serve files in subdirectories."""

    # Create a nested directory structure
    subdir = reports_dir / "subdir" / "nested"
    subdir.mkdir(parents=True)

    report_content = "<html><body>Nested Report</body></html>"
    report_file = subdir / "nested_report.html"
    report_file.write_text(report_content)

    # Access the nested report as admin
    admin = app.client("admin@website.web")
    response = admin.get("/reports/subdir/nested/nested_report.html")

    assert response.status_code == 200
    assert response.text == report_content


def test_reports_endpoint_handles_missing_file(app, reports_dir):
    """Test that the reports endpoint returns 404 for missing files."""

    admin = app.client("admin@website.web")
    response = admin.get("/reports/nonexistent.html", expect=404)

    assert response.status_code == 404
    assert response.json()["detail"] == "Report not found"


def test_reports_endpoint_prevents_path_traversal(app, reports_dir):
    """Test that the reports endpoint prevents directory traversal attacks."""

    # Create a file outside the reports directory
    parent_dir = reports_dir.parent
    sensitive_file = parent_dir / "sensitive.txt"
    sensitive_file.write_text("Sensitive content")

    admin = app.client("admin@website.web")

    # Try various path traversal attempts
    paths = [
        "../sensitive.txt",
        "../../sensitive.txt",
        "subdir/../../sensitive.txt",
        "../../../etc/passwd",
    ]

    for path in paths:
        response = admin.get(f"/reports/{path}", expect=404)
        assert response.status_code == 404
        # FastAPI may normalize paths or return different error messages
        # The important thing is that we get a 404
        assert response.json()["detail"] in ["Report not found", "Not Found"]


def test_reports_endpoint_rejects_directory_access(app, reports_dir):
    """Test that the reports endpoint rejects attempts to access directories."""

    # Create a subdirectory
    subdir = reports_dir / "subdir"
    subdir.mkdir(exist_ok=True)

    admin = app.client("admin@website.web")
    response = admin.get("/reports/subdir", expect=404)

    assert response.status_code == 404
    assert response.json()["detail"] == "Report not found"


def test_reports_endpoint_serves_various_file_types(app, reports_dir):
    """Test that the reports endpoint can serve various file types and sets correct mime types."""

    admin = app.client("admin@website.web")

    # Test HTML file
    html_file = reports_dir / "report.html"
    html_file.write_text("<html><body>HTML</body></html>")
    response = admin.get("/reports/report.html")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")

    # Test JSON file
    json_file = reports_dir / "data.json"
    json_file.write_text('{"key": "value"}')
    response = admin.get("/reports/data.json")
    assert response.status_code == 200
    # Accept FastAPI default ("application/json") and also potential variants
    assert response.headers["content-type"].split(";")[0].strip() == "application/json"

    # Test text file
    txt_file = reports_dir / "notes.txt"
    txt_file.write_text("Some notes")
    response = admin.get("/reports/notes.txt")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")

    # Test CSV file
    csv_file = reports_dir / "data.csv"
    csv_file.write_text("col1,col2\nval1,val2")
    response = admin.get("/reports/data.csv")
    assert response.status_code == 200
    # Accept "text/csv" as main match
    assert response.headers["content-type"].startswith("text/csv")
