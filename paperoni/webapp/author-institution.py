"""Simple search app.
Run with `uvicorn apps.search:app`
"""

import asyncio
import os
from datetime import datetime
from hashlib import md5
from pathlib import Path

from hrepr import H
from sqlalchemy import select
from starbear import ClientWrap, Queue, bear

from ..config import load_config
from ..db import schema as sch
from ..model import Institution, Role, UniqueAuthor
from ..utils import tag_uuid
from .common import mila_template, regenerator

here = Path(__file__).parent


@bear
@mila_template
async def app(page, box):
    """Edit/update the list of researchers."""
    q = Queue()
    debounced = ClientWrap(q, debounce=0.3, form=True)
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
    form = H.form(id="addform", autocomplete="off")["addform"](
        H.input(
            id="formname", name="name", placeholder="Name", oninput=debounced
        )["authorinput"],
        "Role",
        H.select(name="role")["roleinput"](
            [H.option(value=role)(role) for role in roles]
        ),
        "Start date",
        H.input(type="date", id="start", name="date-start")[
            "calender", "authorinput"
        ],
        "End date",
        H.input(type="date", id="end", name="date-end")[
            "calender", "authorinput"
        ],
        H.br,
        H.button("Add")["button"],
        onsubmit=debounced,
    )
    area = H.div["area-authorlink"](
        H.div["up"](
            H.div["column"]("Nom"),
            H.div["column"]("Role"),
            H.div["column"]("Start"),
            H.div["column"]("End"),
            H.div["column"](" Semantic Scholar Ids"),
            H.div["column"](" Openreview Ids"),
        ),
        H.div(id="mid-div")["mid"](),
        H.div(id="down-div")["down"](form),
    ).autoid()
    box.print(area)
    dataAuthors = {}

    def regen(event=None, db=None):
        name = None
        if event is not None:
            name = event["name"]
        if event is not None and event["$submit"] == True:
            name = None
            addAuthor(event)
        return generate(name, db=db)

    def addAuthor(event):
        name = event["name"]
        role = event["role"]
        start_date = event["date-start"]
        end_date = event["date-end"]
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
            page["#addform"].clear()
            page["#down-div"].print(form)

        else:
            page["#down-div"].print(
                H.span(id="errormessage")(
                    "Error : Name, Role and Start date is required"
                )
            )

    async def clickAuthor(id=None):
        startdate = dataAuthors[id]["start"].strftime("%Y-%m-%d")
        enddate = ""
        if dataAuthors[id]["end"] != "":
            enddate = dataAuthors[id]["end"].strftime("%Y-%m-%d")

        filledForm = H.form(id="addform", autocomplete="off")["addform"](
            H.input(
                id="formname",
                name="name",
                placeholder="Name",
                value=dataAuthors[id]["nom"],
                oninput=debounced,
            )["authorinput"],
            "Role",
            H.select(name="role")["roleinput"](
                [
                    H.option(value=role, selected="selected")(role)
                    if role == dataAuthors[id]["role"]
                    else H.option(value=role)(role)
                    for role in roles
                ]
            ),
            "Start date",
            H.input(
                type="date", id="start", name="date-start", value=startdate
            )["calender", "authorinput"],
            "End date",
            H.input(type="date", id="end", name="date-end", value=enddate)[
                "calender", "authorinput"
            ],
            H.br,
            H.button("Add")["button"],
            onsubmit=debounced,
        )
        page["#addform"].clear()
        page["#down-div"].print(filledForm)

    def get_type_links(author, type):
        num_links = 0
        for i in author.links:
            if i.type == type:
                num_links += 1
        return num_links

    def htmlAuthor(result):
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
        page["#mid-div"].print(
            H.div(onclick=lambda event, id=id: clickAuthor(id))[
                "author-column"
            ](
                H.div(id="authorname")["column-mid"](
                    H.span(id="autspan")(author.name)
                ),
                H.div["column-mid"](H.span["align-mid"](result.role)),
                H.div["column-mid"](H.span["align-mid"](date_start)),
                H.div["column-mid"](H.span["align-mid"](date_end)),
            ),
            H.div["column-mid-link"](
                get_type_links(author, "semantic_scholar"),
                onclick="window.open('http://localhost:8000/find-authors-ids?scrapper=semantic_scholar&author="
                + str(author.name)
                + "');",
            ),
            H.div["column-mid-link"](
                get_type_links(author, "openreview"),
                onclick="window.open('http://localhost:8000/find-authors-ids?scraper=openreview&author="
                + str(author.name)
                + "');",
            ),
        )

    def generate(name=None, db=None):
        stmt = select(sch.AuthorInstitution)
        stmt = stmt.join(sch.Author)
        stmt = stmt.order_by(sch.Author.name)
        if not (name == "" or name is None):
            stmt = stmt.filter(sch.Author.name.like(f"%{name}%"))
        results = list(db.session.execute(stmt))

        for (r,) in results:
            yield r

    with load_config(os.environ["PAPERONI_CONFIG"]) as cfg:
        with cfg.database as db:
            regen = regenerator(
                queue=q,
                regen=regen,
                reset=page["#mid-div"].clear,
                db=db,
            )
            async for result in regen:
                htmlAuthor(result)


ROUTES = app
