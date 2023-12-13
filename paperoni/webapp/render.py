from hrepr import H

from ..display import expand_links
from ..model import DatePrecision
from .common import config
from .utils import Confidence


def _score_class(score):
    if score >= 10:
        return "excellent"
    elif score >= 2:
        return "good"
    elif score > 0:
        return "known"
    else:
        return "unknown"


def _paper_score_class(score):
    if score >= 10:
        return "excellent"
    elif score >= 5:
        return "good"
    elif score >= 2:
        return "ok"
    elif score == 1:
        return "poor"
    else:
        return "unknown"


def author_html(auth):
    if not auth.author:  # pragma: no cover
        return H.span["author"]("[ERROR]")
    bio = [
        f"https://mila.quebec/?p={l.link}"
        for l in auth.author.links
        if l.type == "wpid_en"
    ]
    if bio:
        bio = bio[0]
        authname = H.a["author-name"](auth.author.name, href=bio)
    else:
        authname = H.span["author-name"](auth.author.name)

    return H.span["author"](
        authname,
        [H.span["affiliation"](aff.name) for aff in auth.affiliations],
    )


def validation_html(paper, maxauth=50):
    # It seems config.tweaks is a dictionary, not an object.
    # So, we must get "low_confidence_authors" as a key, not as an attribute.
    low_confidence = config().tweaks.get("low_confidence_authors", ())
    c = Confidence(
        institution_name=r".*\bmila\b.*|.*montr.al institute.*learning algorithm.*",
        boost_link_type="wpid_en",
        low_confidence_names=low_confidence,
    )

    def _domain(lnk):
        return lnk.split("/")[2]

    venues = H.div["venues"]
    for release in paper.releases:
        v = release.venue
        venues = venues(
            H.div["venue"](
                H.span["venue-date"](
                    DatePrecision.format(v.date, v.date_precision)
                ),
                H.span["venue-name"](v.name),
                H.span["venue-status"](release.status),
            )
        )

    nauth = len(paper.authors)
    more = nauth - maxauth if nauth > maxauth else 0
    pdfs = [lnk for k, lnk in expand_links(paper.links) if "pdf" in lnk]

    total_score, author_scores = c.paper_score(paper)

    if hasattr(paper, "excerpt"):
        before, matching, after = paper.excerpt
        excerpt = H.div["excerpt"](before, H.b(matching), after)
    else:
        excerpt = ""

    return H.div["paper", "validation", _paper_score_class(total_score)](
        H.div["band"](int(total_score)),
        H.div["content"](
            H.div["title"](
                H.a(paper.title, href=pdfs[0], target="_blank")
                if pdfs
                else paper.title
            ),
            H.div["authors"](
                [
                    author_html(auth)[_score_class(score)]
                    for auth, score in author_scores[:maxauth]
                ],
                f"... ({more} more)" if more else "",
            ),
            venues,
            H.div["topics"](H.div["topic"](t.name) for t in paper.topics),
            H.div["extra"](
                H.a["link"](
                    _domain(link) if typ == "html" else typ.replace("_", "-"),
                    href=link,
                    target="_blank",
                )
                for typ, link in expand_links(paper.links)
                if link.startswith("http")
            ),
            excerpt,
        ),
    )


def paper_html(paper, maxauth=50):
    def _domain(lnk):
        return lnk.split("/")[2]

    venues = H.div["venues"]
    for release in paper.releases:
        v = release.venue
        venues = venues(
            H.div["venue"](
                H.span["venue-date"](
                    DatePrecision.format(v.date, v.date_precision)
                ),
                H.span["venue-name"](v.name),
                H.span["venue-status"](release.status),
            )
        )

    nauth = len(paper.authors)
    more = nauth - maxauth if nauth > maxauth else 0
    pdfs = [lnk for k, lnk in expand_links(paper.links) if "pdf" in lnk]

    if hasattr(paper, "excerpt"):
        before, matching, after = paper.excerpt
        excerpt = H.div["excerpt"](before, H.b(matching), after)
    else:
        excerpt = ""

    return H.div["paper"](
        H.div["content"](
            H.div["title"](
                H.a(paper.title, href=pdfs[0], target="_blank")
                if pdfs
                else paper.title
            ),
            H.div["authors"](
                [author_html(auth) for auth in paper.authors],
                f"... ({more} more)" if more else "",
            ),
            venues,
            H.div["topics"](H.div["topic"](t.name) for t in paper.topics),
            H.div["extra"](
                H.a["link"](
                    _domain(link) if typ == "html" else typ.replace("_", "-"),
                    href=link,
                    target="_blank",
                )
                for typ, link in expand_links(paper.links)
                if link.startswith("http")
            ),
            excerpt,
        ),
    )
