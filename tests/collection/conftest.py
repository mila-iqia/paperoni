import pytest


def pytest_configure(config: pytest.Config):
    config.addinivalue_line(
        "markers", "coll_w_remote: mark test to also run with the remote collection"
    )
