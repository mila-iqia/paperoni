import datetime
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
from serieux import serialize
from serieux.features.partial import Override

from paperoni.model.classes import Author, Link, Paper, PaperAuthor
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
    assert (
        _suggest_flag(validator.get("/my-papers", suggest="1", expect=200).text) is True
    )
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
        "No papers claimed.",
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

    claimed = validator.get("/api/v1/search", author=email, expect=200).json()
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

    unclaimed = validator.get("/api/v1/search", author=email, expect=200).json()
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

    pending = seeker.get("/api/v1/pending/list", author=email, expect=200).json()
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
    latest = validator.get(
        f"/api/v1/paper/{paper['id']}", latest_edit="true", expect=200
    ).json()
    assert all(a["author"]["email"] != email for a in latest["authors"])


# ---------------------------------------------------------------------------
# Claim / unclaim submissions must not clobber the paper's links
# ---------------------------------------------------------------------------

SEEDED_LINKS = [
    ("arxiv", "2106.09685"),
    ("doi", "10.1234/abcdef"),
    ("pdf.official", "https://example.org/paper.pdf"),
    ("url", "https://example.org/project-page"),
]

TITLE_WITH_LINKS = "Link Preservation Under Claim Submission"


def _link_pairs(paper_json):
    return {(l["type"], l["link"]) for l in paper_json.get("links", [])}


def _seed_linked_paper(client):
    """Add a paper whose canonical links include both identifier links
    (arxiv/doi, which expand into generated URLs) and plain links (pdf.official
    / url, which have no generated URL at all)."""
    paper = Paper(
        title=TITLE_WITH_LINKS,
        authors=[
            PaperAuthor(
                display_name="Ada Lovelace",
                author=Author(name="Ada Lovelace"),
            )
        ],
        links=[Link(type=t, link=l) for t, l in SEEDED_LINKS],
    )
    response = client.post(
        "/api/v1/include", papers=[serialize(Paper, paper)], expect=200
    )
    return response.json()["ids"][0]


def test_claim_preserves_links(wr_app_with_suggestions):
    """Regression test: claiming from My Papers submits the whole paper, and
    /include replaces the stored document wholesale. The claim flow therefore
    bases its submission on the unexpanded copy from /api/v1/paper/{id} (see
    fetchCanonicalPaper in my_papers.js), not on the search result it displays,
    which carries display-expanded links."""
    validator = wr_app_with_suggestions.client("validator@website.web")
    pid = _seed_linked_paper(validator)

    canonical = validator.get(f"/api/v1/paper/{pid}", expect=200).json()
    assert _link_pairs(canonical) == set(SEEDED_LINKS)

    # The My Papers display form (expand_links=true) swaps identifier links for
    # generated URLs and drops links without one -- it must never be submitted
    # back (see the hazard documented in the test below).
    search = validator.get(
        "/api/v1/search", title=TITLE_WITH_LINKS, expand_links="true", expect=200
    ).json()
    (displayed,) = search["results"]
    assert str(displayed["id"]) == str(pid)
    view = _link_pairs(displayed)
    assert ("arxiv", "2106.09685") not in view
    assert ("url", "https://example.org/project-page") not in view

    # The claim itself, as fixed: base on the canonical copy, set the email,
    # submit.
    claim = canonical
    claim["authors"][0]["author"]["email"] = "validator@website.web"
    result = validator.post(
        "/api/v1/include",
        papers=[claim],
        comment="Claimed via My Papers",
        expect=200,
    ).json()
    assert result["success"] is True

    after = validator.get(f"/api/v1/paper/{pid}", expect=200).json()
    assert _link_pairs(after) == set(SEEDED_LINKS)
    assert after["authors"][0]["author"]["email"] == "validator@website.web"


def test_suggested_claim_preserves_links(wr_app_with_suggestions):
    """Same regression for the non-validator flow: the suggestion is built from
    the canonical copy, and approving it into the collection (a wholesale
    replace) must leave the links intact."""
    validator = wr_app_with_suggestions.client("validator@website.web")
    seeker = wr_app_with_suggestions.client("seeker@website.web")
    pid = _seed_linked_paper(validator)

    canonical = seeker.get(f"/api/v1/paper/{pid}", expect=200).json()
    canonical["authors"][0]["author"]["email"] = "seeker@website.web"
    result = seeker.post(
        "/api/v1/suggest",
        papers=[canonical],
        comment="Claimed via My Papers",
        expect=200,
    ).json()
    assert result["success"] is True

    decision = validator.post(
        "/api/v1/pending/decide", approve=[str(pid)], reject=[], expect=200
    ).json()
    assert decision["success"] is True

    after = validator.get(f"/api/v1/paper/{pid}", expect=200).json()
    assert _link_pairs(after) == set(SEEDED_LINKS)
    assert after["authors"][0]["author"]["email"] == "seeker@website.web"


def test_suggested_comment_is_stamped(wr_app_with_suggestions):
    """Comments recorded in the DB alongside a suggestion carry the user, the
    description, and a UTC timestamp."""
    validator = wr_app_with_suggestions.client("validator@website.web")
    seeker = wr_app_with_suggestions.client("seeker@website.web")
    pid = _seed_linked_paper(validator)

    result = seeker.post(
        "/api/v1/suggest",
        papers=[seeker.get(f"/api/v1/paper/{pid}", expect=200).json()],
        comment="Please add the conference version",
        expect=200,
    ).json()
    assert result["success"] is True

    suggestion = seeker.get(f"/api/v1/paper/{pid}", latest_edit="true", expect=200).json()
    (comment,) = suggestion["info"]["comments"]
    assert comment["user"] == "seeker@website.web"
    assert comment["comment"] == "Please add the conference version"
    stamp = datetime.datetime.fromisoformat(comment["timestamp"])
    assert stamp.tzinfo == datetime.timezone.utc
    now = datetime.datetime.now(datetime.timezone.utc)
    assert abs(now - stamp) < datetime.timedelta(minutes=5)


def test_approval_preserves_comments(wr_app_with_suggestions):
    """Approval copies the suggestion document into the collection verbatim,
    so the comment history (user / comment / timestamp) survives the approval
    and keeps accumulating across subsequent suggest/approve cycles."""
    validator = wr_app_with_suggestions.client("validator@website.web")
    seeker = wr_app_with_suggestions.client("seeker@website.web")
    pid = _seed_linked_paper(validator)

    canonical = seeker.get(f"/api/v1/paper/{pid}", expect=200).json()
    assert (
        seeker.post(
            "/api/v1/suggest",
            papers=[canonical],
            comment="Adding the arxiv release",
            expect=200,
        ).json()["success"]
        is True
    )
    assert (
        validator.post(
            "/api/v1/pending/decide", approve=[str(pid)], reject=[], expect=200
        ).json()["success"]
        is True
    )

    # The approved paper in the collection carries the comment.
    approved = validator.get(f"/api/v1/paper/{pid}", expect=200).json()
    (first,) = approved["info"]["comments"]
    assert first["user"] == "seeker@website.web"
    assert first["comment"] == "Adding the arxiv release"
    datetime.datetime.fromisoformat(first["timestamp"])

    # The suggestion was consumed.
    pending = validator.get("/api/v1/pending/list", expect=200).json()
    assert all(
        not (d["new"] and str(d["new"]["id"]) == str(pid)) for d in pending["results"]
    )

    # A later suggestion built on the approved copy carries the history
    # forward and appends to it.
    approved["authors"][0]["author"]["email"] = "seeker@website.web"
    assert (
        seeker.post(
            "/api/v1/suggest",
            papers=[approved],
            comment="Claimed via My Papers",
            expect=200,
        ).json()["success"]
        is True
    )
    assert (
        validator.post(
            "/api/v1/pending/decide", approve=[str(pid)], reject=[], expect=200
        ).json()["success"]
        is True
    )

    final = validator.get(f"/api/v1/paper/{pid}", expect=200).json()
    assert [c["comment"] for c in final["info"]["comments"]] == [
        "Adding the arxiv release",
        "Claimed via My Papers",
    ]


def test_expanded_paper_roundtrip_is_lossy(wr_app_with_suggestions):
    """Documents the hazard the claim flow avoids: submitting a display-expanded
    paper wipes links because /include replaces the whole document. If expansion
    ever becomes round-trip safe, this test failing is the cue to drop the
    client-side refetch in fetchCanonicalPaper (my_papers.js)."""
    validator = wr_app_with_suggestions.client("validator@website.web")
    pid = _seed_linked_paper(validator)

    displayed = validator.get(
        "/api/v1/search", title=TITLE_WITH_LINKS, expand_links="true", expect=200
    ).json()["results"][0]
    displayed["authors"][0]["author"]["email"] = "validator@website.web"
    validator.post(
        "/api/v1/include",
        papers=[displayed],
        comment="The old buggy claim",
        expect=200,
    )

    after = validator.get(f"/api/v1/paper/{pid}", expect=200).json()
    # The claim went through, but the canonical links are gone.
    assert after["authors"][0]["author"]["email"] == "validator@website.web"
    assert ("arxiv", "2106.09685") not in _link_pairs(after)
    assert ("url", "https://example.org/project-page") not in _link_pairs(after)
