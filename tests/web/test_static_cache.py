import httpx


def test_static_assets_are_no_cache(app):
    """Static assets (CSS/JS) must carry Cache-Control: no-cache so browsers
    always revalidate against the server's ETag/Last-Modified instead of
    trusting a stale cached copy after a deploy (which otherwise only a hard
    refresh would fix)."""
    resp = httpx.get(f"{app}/assets/style.css")
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "no-cache"
    # Revalidation machinery must still be present for the no-cache directive
    # to be cheap (a 304, not a full re-download every time).
    assert resp.headers.get("etag") or resp.headers.get("last-modified")

    resp = httpx.get(f"{app}/assets/my_papers.js")
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "no-cache"


def test_static_asset_revalidation_returns_304(app):
    resp = httpx.get(f"{app}/assets/style.css")
    etag = resp.headers.get("etag")
    assert etag

    revalidated = httpx.get(f"{app}/assets/style.css", headers={"If-None-Match": etag})
    assert revalidated.status_code == 304


def test_non_static_responses_are_unaffected(app):
    resp = httpx.get(f"{app}/api/v1")
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") != "no-cache"
