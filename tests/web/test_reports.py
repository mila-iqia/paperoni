"""
Tests for the logs serving route.
"""

import pytest

from paperoni.config import config

log_content = '{"event": "test", "timestamp": "2024-01-01T00:00:00"}'


@pytest.fixture
def logs_dir():
    logs_dir = config.data_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    yield logs_dir


@pytest.fixture
def simple_log(logs_dir):
    name = "test_log.jsonl"
    log_file = logs_dir / name
    log_file.write_text('{"event": "test", "timestamp": "2024-01-01T00:00:00"}')
    yield name


def test_logs_endpoint_requires_dev_capability(app, simple_log):
    """Test that the logs endpoint requires dev capability."""

    # Test unauthenticated access
    unlogged = app.client()
    response = unlogged.get(f"/logs/{simple_log}", expect=401)
    assert "Authentication required" in response.json()["detail"]

    # Test with user without dev capability
    user = app.client("seeker@website.web")
    response = user.get(f"/logs/{simple_log}", expect=403)
    assert "dev capability required" in response.json()["detail"]

    # Test with admin user (should have dev capability)
    admin = app.client("admin@website.web")
    response = admin.get(f"/logs/{simple_log}")
    assert response.status_code == 200


def test_logs_endpoint_serves_log_file(app, simple_log):
    """Test that the logs endpoint correctly serves a log file."""

    # Access the log as admin
    admin = app.client("admin@website.web")
    response = admin.get(f"/logs/{simple_log}")

    assert response.status_code == 200
    assert response.text == log_content


def test_logs_endpoint_serves_nested_files(app, logs_dir):
    """Test that the logs endpoint can serve files in subdirectories."""

    # Create a nested directory structure
    subdir = logs_dir / "subdir" / "nested"
    subdir.mkdir(parents=True)

    nested_log_content = '{"event": "nested", "data": "test"}'
    log_file = subdir / "nested_log.jsonl"
    log_file.write_text(nested_log_content)

    # Access the nested log as admin
    admin = app.client("admin@website.web")
    response = admin.get("/logs/subdir/nested/nested_log.jsonl")

    assert response.status_code == 200
    assert response.text == nested_log_content


def test_logs_endpoint_handles_missing_file(app, logs_dir):
    """Test that the logs endpoint returns 404 for missing files."""

    admin = app.client("admin@website.web")
    response = admin.get("/logs/nonexistent.jsonl", expect=404)

    assert response.status_code == 404
    assert response.json()["detail"] == "Report not found"


def test_logs_endpoint_prevents_path_traversal(app, logs_dir):
    """Test that the logs endpoint prevents directory traversal attacks."""

    # Create a file outside the logs directory
    parent_dir = logs_dir.parent
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
        response = admin.get(f"/logs/{path}", expect=404)
        assert response.status_code == 404
        # FastAPI may normalize paths or return different error messages
        # The important thing is that we get a 404
        assert response.json()["detail"] in ["Report not found", "Not Found"]


def test_logs_endpoint_rejects_directory_access(app, logs_dir):
    """Test that the logs endpoint rejects attempts to access directories."""

    # Create a subdirectory
    subdir = logs_dir / "subdir"
    subdir.mkdir(exist_ok=True)

    admin = app.client("admin@website.web")
    response = admin.get("/logs/subdir", expect=404)

    assert response.status_code == 404
    assert response.json()["detail"] == "Report not found"


def test_logs_endpoint_serves_various_file_types(app, logs_dir):
    """Test that the logs endpoint can serve various file types and sets correct mime types."""

    admin = app.client("admin@website.web")

    # Test JSONL file (typical log file)
    jsonl_file = logs_dir / "events.jsonl"
    jsonl_file.write_text('{"event": "start"}\n{"event": "end"}')
    response = admin.get("/logs/events.jsonl")
    assert response.status_code == 200
    # JSONL files may be served as application/octet-stream or text/plain
    assert response.headers["content-type"] in [
        "application/octet-stream",
        "text/plain",
        "text/plain; charset=utf-8",
    ]

    # Test JSON file
    json_file = logs_dir / "data.json"
    json_file.write_text('{"key": "value"}')
    response = admin.get("/logs/data.json")
    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0].strip() == "application/json"

    # Test text file
    txt_file = logs_dir / "debug.txt"
    txt_file.write_text("Debug output")
    response = admin.get("/logs/debug.txt")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")

    # Test log file
    log_file = logs_dir / "application.log"
    log_file.write_text("[INFO] Application started\n[ERROR] Connection failed")
    response = admin.get("/logs/application.log")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
