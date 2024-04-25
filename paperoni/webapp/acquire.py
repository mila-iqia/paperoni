from pathlib import Path

from hrepr import H
from openreview.openreview import OpenReviewException
from starbear import Queue

from ..config import papconf
from ..model import Flag
from ..sources.scrapers.openreview import OpenReviewScraperBase
from ..sources.scrapers.openreview2 import (
    OpenReviewScraperBase as OpenReviewScraperBase2,
)
from ..sources.scrapers.semantic_scholar import SemanticScholarQueryManager
from .common import mila_template

here = Path(__file__).parent


@mila_template(title="Add papers", help="/help#add-papers")
async def app(page, box):
    """Add papers using their Semantic Scholar ID."""
    q = Queue()

    form = H.form["sql-edit"](
        H.div(H.textarea(name="refs")),
        H.div(
            H.input(type="checkbox", name="validate", checked=True),
            "Auto-validate",
        ),
        H.div(H.button("Add")),
        onsubmit=q.wrap(form=True),
    )
    box.print(form)
    box.print(results := H.div().autoid())

    with papconf.database as db:
        ss = SemanticScholarQueryManager()
        orv = OpenReviewScraperBase(config=papconf, db=db)
        orv2 = OpenReviewScraperBase2(config=papconf, db=db)

        async for event in q:
            box[results].clear()
            for paper in event["refs"].split("\n"):
                if "semanticscholar" in paper:
                    typ = "semantic_scholar"
                elif "semantic_scholar" in paper:
                    typ = "semantic_scholar"
                elif "openreview" in paper:
                    typ = "openreview"
                else:
                    box[results].print(f"Please specify source for {paper}")
                ref = paper and paper.split("/")[-1]
                ref = ref and ref.split("?id=")[-1]
                if ref:
                    box[results].print(H.div(f"Trying to acquire: {typ}:{ref}"))
                    if typ == "semantic_scholar":
                        paper = ss.paper(paper_id=ref)
                    elif typ == "openreview":
                        paper = None
                        try:
                            for paper in orv._query({"id": ref}, limit=1):
                                break
                        except OpenReviewException:
                            try:
                                for paper in orv2._query({"id": ref}, limit=1):
                                    break
                            except OpenReviewException:
                                pass
                    if paper:
                        if results["validate"]:
                            paper.flags.append(
                                Flag(flag_name="validation", flag=True)
                            )
                        db.acquire(paper)
                        box[results].print(H.div(f"Acquired: {typ}:{ref}"))
                    else:
                        box[results].print(
                            H.div(f"Could not acquire: {typ}:{ref}")
                        )


ROUTES = app
