import re
import shutil
import tempfile
from contextlib import contextmanager
from functools import partial
from pathlib import Path

import gifnoc
import httpx
import pytest
from easy_oauth.testing.utils import AppTester
from serieux.features.partial import Override

from tests.web.conftest import here


@contextmanager
def _wrap_with_suggestions(cfg_src, collfile, suggestionsfile):
    tmp_path = Path(tempfile.mkdtemp())
    additional = {
        "paperoni.work_file": str(tmp_path / "work.yaml"),
        "paperoni.collection": {
            "$class": "paperoni.collection.filecoll:FileCollection",
            "file": str(collfile),
        },
        "paperoni.suggestions": {
            "$class": "paperoni.collection.filecoll:FileCollection",
            "file": str(suggestionsfile),
        },
        "paperoni.focuses": Override(str(tmp_path / "focuses.yaml")),
    }
    with gifnoc.use(*cfg_src, additional):
        yield


@pytest.fixture
def wr_app_with_suggestions(oauth_mock, cfg_src, tmp_path):
    """Like `wr_app`, but also configures a (file-backed) suggestions collection,
    which the shared test config leaves unset."""
    from paperoni.web import create_app

    src_collfile = here / ".." / "data" / "papers.yaml"
    collfile = tmp_path / "papers.yaml"
    shutil.copy(str(src_collfile), str(collfile))
    suggestionsfile = tmp_path / "suggestions.yaml"

    with AppTester(
        create_app(),
        oauth_mock,
        wrap=partial(_wrap_with_suggestions, cfg_src, collfile, suggestionsfile),
    ) as appt:
        yield appt


def _suggest_flag(resp_text):
    call = re.search(r"displayMyPapers\([^;]*\);", resp_text).group()
    if re.search(r",\s*true\s*\)", call):
        return True
    if re.search(r",\s*false\s*\)", call):
        return False
    raise AssertionError(f"could not find suggest flag in {call!r}")


def test_my_papers_suggest_flag(app):
    """Non-validators must get suggest=true (their claim/unclaim/add-paper
    actions go through /api/v1/suggest, not the direct /api/v1/include)."""
    seeker = app.client("seeker@website.web")
    assert _suggest_flag(seeker.get("/my-papers", expect=200).text) is True

    validator = app.client("validator@website.web")
    assert _suggest_flag(validator.get("/my-papers", expect=200).text) is False


def test_my_papers_suggest_param_override(app):
    """?suggest=1/0 overrides the default, e.g. so a validator can test the
    suggestion flow without giving up their validate capability."""
    validator = app.client("validator@website.web")
    assert _suggest_flag(validator.get("/my-papers", suggest="1", expect=200).text) is True
    assert _suggest_flag(validator.get("/my-papers", expect=200).text) is False

    seeker = app.client("seeker@website.web")
    assert _suggest_flag(seeker.get("/my-papers", suggest="0", expect=200).text) is False


def test_my_papers_smoke(app):
    user = app.client("seeker@website.web")

    resp = user.get("/my-papers", expect=200)
    assert "My Papers" in resp.text
    assert 'id="title"' in resp.text
    assert 'id="author"' in resp.text
    assert 'id="claimForEmail"' in resp.text
    assert "displayMyPapers" in resp.text

    resp2 = httpx.get(f"{app}/assets/my_papers.js")
    assert resp2.status_code == 200
    assert "export function displayMyPapers" in resp2.text

    # The dictionary must carry every new user-facing string this page adds.
    dictionary = httpx.get(f"{app}/assets/translate.json").json()
    keys_en = {e["en"] for e in dictionary}
    for key in [
        "My Papers",
        "Claiming for",
        "Click to edit",
        "Claim",
        "Not mine",
        "Confirm",
        "Cancel",
        "Which author are you?",
        "Unclaimed papers",
        "No papers found for your account.",
        "No unclaimed papers found.",
        "Nothing to unclaim",
        "Paper unclaimed",
        "Failed to unclaim: {1}",
        "This paper has no authors to claim",
        "Paper claimed",
        "Failed to claim: {1}",
        "Add Paper",
        "Search by title first",
        "Unclaimed via My Papers",
        "Claimed via My Papers",
    ]:
        assert key in keys_en, f"Missing translation entry for {key!r}"
        entry = next(e for e in dictionary if e["en"] == key)
        assert entry.get("fr"), f"Missing French translation for {key!r}"

    unlogged = app.client()
    unlogged.get("/my-papers", expect=307)


def test_my_papers_claim_unclaim_flow(wr_app):
    email = "olivier.breuleux@mila.quebec"

    # validator has the `validate` capability -> direct /include, like a
    # non-suggest edit.
    validator = wr_app.client("validator@website.web")

    search = validator.get("/api/v1/search", limit=1, expect=200).json()
    assert search["results"], "expected at least one paper in the test collection"
    paper = search["results"][0]
    assert paper["authors"], "expected the sample paper to have authors"

    # Simulate a "claim": set the first author's email to the user's email.
    paper["authors"][0]["author"]["email"] = email
    result = validator.post(
        "/api/v1/include",
        papers=[paper],
        comment="",
        expect=200,
    ).json()
    assert result["success"]

    claimed = validator.get(
        "/api/v1/search", author=email, expect=200
    ).json()
    assert claimed["total"] >= 1
    assert any(p["id"] == paper["id"] for p in claimed["results"])

    # Simulate an "unclaim": replace the matching author's email with "n/a".
    refetched = validator.get(f"/api/v1/paper/{paper['id']}", expect=200).json()
    matches = [a for a in refetched["authors"] if a["author"]["email"] == email]
    assert matches
    for a in matches:
        a["author"]["email"] = "n/a"
    result = validator.post(
        "/api/v1/include",
        papers=[refetched],
        comment="",
        expect=200,
    ).json()
    assert result["success"]

    unclaimed = validator.get(
        "/api/v1/search", author=email, expect=200
    ).json()
    assert unclaimed["total"] == 0

    final = validator.get(f"/api/v1/paper/{paper['id']}", expect=200).json()
    assert all(a["author"]["email"] != email for a in final["authors"])
    assert any(a["author"]["email"] == "n/a" for a in final["authors"])


def test_my_papers_claim_via_suggest(wr_app_with_suggestions):
    email = "olivier.breuleux@mila.quebec"

    # seeker only has `search` -> should go through /suggest (pending), like
    # a suggest-mode edit.
    seeker = wr_app_with_suggestions.client("seeker@website.web")

    search = seeker.get("/api/v1/search", limit=1, expect=200).json()
    paper = search["results"][0]
    paper["authors"][0]["author"]["email"] = email

    result = seeker.post(
        "/api/v1/suggest",
        papers=[paper],
        comment="Claimed via My Papers",
        expect=200,
    ).json()
    assert result["success"]

    pending = seeker.get(
        "/api/v1/pending/list", author=email, expect=200
    ).json()
    assert pending["total"] >= 1


def test_my_papers_unclaim_via_suggest_leaves_main_db_stale(wr_app_with_suggestions):
    """Documents the bug the localStorage workaround in my_papers.js works
    around: a non-validator's "unclaim" only lands in the suggestions db, so
    the main collection (and thus a plain /api/v1/search) still shows the
    paper as claimed. ?latest_edit=true is the only way to see the real,
    pending-aware state -- which is exactly what the client re-checks for any
    paper id it locally remembers unclaiming this way."""
    email = "olivier.breuleux@mila.quebec"
    validator = wr_app_with_suggestions.client("validator@website.web")
    seeker = wr_app_with_suggestions.client("seeker@website.web")

    # Claim a paper directly (as if done by a validator, or already approved).
    search = validator.get("/api/v1/search", limit=1, expect=200).json()
    paper = search["results"][0]
    paper["authors"][0]["author"]["email"] = email
    validator.post("/api/v1/include", papers=[paper], comment="", expect=200)

    # Now suggest unclaiming it (as a non-validator would via the "Not mine" button).
    unclaim_suggestion = validator.get(f"/api/v1/paper/{paper['id']}", expect=200).json()
    for a in unclaim_suggestion["authors"]:
        if a["author"]["email"] == email:
            a["author"]["email"] = "n/a"
    result = seeker.post(
        "/api/v1/suggest",
        papers=[unclaim_suggestion],
        comment="Unclaimed via My Papers",
        expect=200,
    ).json()
    assert result["success"]

    # The bug: the main collection is untouched, so a plain search still
    # claims it for this email.
    still_claimed = validator.get("/api/v1/search", author=email, expect=200).json()
    assert any(p["id"] == paper["id"] for p in still_claimed["results"])

    # The fix's data source: ?latest_edit=true surfaces the pending
    # suggestion instead, which really does show it as unclaimed.
    latest = validator.get(f"/api/v1/paper/{paper['id']}", latest_edit="true", expect=200).json()
    assert all(a["author"]["email"] != email for a in latest["authors"])
