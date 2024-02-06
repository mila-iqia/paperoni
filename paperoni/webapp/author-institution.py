from datetime import datetime
from hashlib import md5
from pathlib import Path

from hrepr import H
from sqlalchemy import select
from starbear import Queue

from ..db import schema as sch
from ..model import Institution, Role, UniqueAuthor
from ..utils import tag_uuid
from .common import (
    BaseGUI,
    SearchElement,
    SelectElement,
    config,
    mila_template,
)

here = Path(__file__).parent


def get_type_links(author, type):
    num_links = 0
    for i in author.links:
        if i.type == type:
            num_links += 1
    return num_links


@mila_template(title="List of researchers", help="/help#author-institution")
async def app(page, box):
    """Edit/update the list of researchers."""
    q = Queue()
    roles = [
        "associate",
        "core",
        "chair",
        "idt",
        "art",
        "associate-external",
        "industry-core",
        "industry-associate",
    ]
    gui = BaseGUI(
        elements=[
            SearchElement(
                name="name",
                description="Name",
                default=None,
            ),
            SelectElement(
                name="role",
                description="Role",
                options=roles,
                default=None,
            ),
            SearchElement(
                name="start",
                description="Start date",
                default=None,
                type="date",
            ),
            SearchElement(
                name="end",
                description="End date",
                default=None,
                type="date",
            ),
        ],
        queue=q,
        button_label="Add/Edit",
    )
    form = gui.form()

    area = H.div(
        H.div(id="gui-div")["top-gui"](form),
        table := H.div().autoid(),
    )
    box.print(area)
    dataAuthors = {}

    def addAuthor(event):
        name = event["name"]
        role = event["role"]
        start_date = event["start"]
        end_date = event["end"]
        page["#errormessage"].delete()
        if not (name == "" or role == "" or start_date == ""):
            uaRole = Role(
                institution=Institution(
                    category="academia",
                    name="Mila",
                    aliases=[],
                ),
                role=role,
                start_date=(d := start_date) and f"{d} 00:00",
            )
            if end_date != "":
                uaRole = Role(
                    institution=Institution(
                        category="academia",
                        name="Mila",
                        aliases=[],
                    ),
                    role=role,
                    start_date=(d := start_date) and f"{d} 00:00",
                    end_date=(d := end_date) and f"{d} 00:00",
                )

            ua = UniqueAuthor(
                author_id=tag_uuid(
                    md5(name.encode("utf8")).digest(), "canonical"
                ),
                name=name,
                aliases=[],
                affiliations=[],
                roles=[uaRole],
                links=[],
                quality=(1.0,),
            )
            db.acquire(ua)

            # Reset the form
            gui.clear()
            page["#gui-div"].set(gui.form())

        else:
            page["#gui-div"].print(
                H.span(id="errormessage")(
                    "Error : Name, Role and Start date is required"
                )
            )

    async def clickAuthor(id=None):
        startdate = dataAuthors[id]["start"].strftime("%Y-%m-%d")
        enddate = ""
        if dataAuthors[id]["end"] != "":
            enddate = dataAuthors[id]["end"].strftime("%Y-%m-%d")

        gui.set_params(
            {
                "name": dataAuthors[id]["nom"],
                "role": dataAuthors[id]["role"],
                "start": startdate,
                "end": enddate,
            }
        )
        page["#gui-div"].set(gui.form())

    def author_html(result):
        author = result.author
        date_start = ""
        date_end = ""
        if result.start_date is not None:
            date_start = datetime.fromtimestamp(result.start_date).date()
        if result.end_date is not None:
            date_end = datetime.fromtimestamp(result.end_date).date()
        id = len(dataAuthors)
        dataAuthors[id] = {
            "nom": author.name,
            "role": result.role,
            "start": date_start,
            "end": date_end,
        }
        return H.tr(onclick=lambda event, id=id: clickAuthor(id))(
            H.td(author.name),
            H.td(result.role),
            H.td(date_start),
            H.td(date_end),
            H.td(
                H.div(
                    get_type_links(author, "semantic_scholar"),
                    "⧉",
                    onclick="window.open('/find-authors-ids?scraper=semantic_scholar&author="
                    + str(author.name)
                    + "');",
                )
            ),
            H.td(
                H.div(
                    get_type_links(author, "openreview"),
                    "⧉",
                    onclick="window.open('/find-authors-ids?scraper=openreview&author="
                    + str(author.name)
                    + "');",
                ),
            ),
        )

    def make_table(results):
        return H.table["researchers"](
            H.thead(
                H.tr(
                    H.th("Name"),
                    H.th("Role"),
                    H.th("Start"),
                    H.th("End"),
                    H.th("Semantic Scholar Ids"),
                    H.th("Openreview Ids"),
                )
            ),
            H.tbody([author_html(result) for result in results]),
        )

    def generate(name=None):
        stmt = select(sch.AuthorInstitution)
        stmt = stmt.join(sch.Author)
        stmt = stmt.order_by(sch.Author.name)
        if not (name == "" or name is None):
            stmt = stmt.filter(sch.Author.name.like(f"%{name}%"))
        results = list(db.session.execute(stmt))

        for (r,) in results:
            yield r

    with config().database as db:
        page[table].set(make_table(list(generate(None))))
        async for event in q:
            name = event["name"]
            if event is not None and event.submit == True:
                name = None
                addAuthor(event)
            page[table].set(make_table(list(generate(name))))


ROUTES = app
