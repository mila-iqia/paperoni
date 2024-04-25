from datetime import datetime
from hashlib import md5
from pathlib import Path

from hrepr import H
from sqlalchemy import select
from starbear import Queue

from ..config import papconf
from ..db import schema as sch
from ..model import Institution, Link, Role, UniqueAuthor
from ..utils import tag_uuid
from .common import BaseGUI, SearchElement, SelectElement, mila_template

here = Path(__file__).parent


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
            SearchElement(
                name="milamail",
                description="Mila mail",
                default=None,
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
        email = event["milamail"]
        page["#errormessage"].delete()
        if not (name == "" or role == "" or start_date == ""):
            links = []
            if email != "":
                if "@" not in email:
                    page["#gui-div"].print(
                        H.span(id="errormessage")(
                            "Error: email address should contain a @"
                        )
                    )
                    return
                else:
                    links.append(
                        Link(
                            link=email,
                            type="email.mila",
                        )
                    )

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
            auid = tag_uuid(md5(name.encode("utf8")).digest(), "canonical")
            ua = UniqueAuthor(
                author_id=auid,
                name=name,
                aliases=[],
                affiliations=[],
                roles=[uaRole],
                links=[],
                quality=(1.0,),
            )
            for lnk in links:
                db.insert_author_link(
                    auid, lnk.type, lnk.link, validity=1, exclusive=True
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
                "milamail": dataAuthors[id]["milamail"],
            }
        )
        page["#gui-div"].set(gui.form())

    def get_type_links(author, type):
        q = """
            SELECT count(*)
            FROM author_scrape_ids
            WHERE author_id = :aid
              AND scraper = :type
              AND active = 1
        """
        ((cnt,),) = db.session.execute(
            q, params={"aid": author.author_id, "type": type}
        )
        return cnt

    def author_html(result):
        author = result.author
        date_start = ""
        date_end = ""
        if result.start_date is not None:
            date_start = datetime.fromtimestamp(result.start_date).date()
        if result.end_date is not None:
            date_end = datetime.fromtimestamp(result.end_date).date()
        id = len(dataAuthors)
        email_links = [
            lnk.link for lnk in author.links if lnk.type == "email.mila"
        ]
        email = email_links[0] if email_links else ""
        dataAuthors[id] = {
            "nom": author.name,
            "role": result.role,
            "start": date_start,
            "end": date_end,
            "milamail": email,
        }
        return H.tr(onclick=lambda event, id=id: clickAuthor(id))(
            H.td(author.name),
            H.td(result.role),
            H.td(date_start),
            H.td(date_end),
            H.td["column-email"](email),
            H.td(
                H.div(
                    get_type_links(author, "semantic_scholar"),
                    "⧉",
                    onclick="window.open('/find-authors-ids?cutoff=2022-06-01&scraper=semantic_scholar&author_id="
                    + author.author_id.hex()
                    + "');",
                )
            ),
            H.td(
                H.div(
                    get_type_links(author, "openreview"),
                    "⧉",
                    onclick="window.open('/find-authors-ids?cutoff=2022-06-01&scraper=openreview&author_id="
                    + author.author_id.hex()
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
                    H.th("Email"),
                    H.th("SS Ids"),
                    H.th("OR Ids"),
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

    with papconf.database as db:
        table_content = make_table(list(generate(None)))
        page[table].set(table_content)
        async for event in q:
            name = event["name"]
            if event is not None and event.submit is True:
                name = None
                addAuthor(event)
            table_content = make_table(list(generate(name)))
            page[table].set(table_content)


ROUTES = app
