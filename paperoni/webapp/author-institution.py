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

from paperoni.config import load_config
from paperoni.db import schema as sch
from paperoni.display import html
from paperoni.model import Institution, Role, UniqueAuthor
from paperoni.utils import tag_uuid

here = Path(__file__).parent


async def regenerator(queue, regen, reset):
    gen = regen()
    done = False
    while True:
        if done:
            inp = await queue.get()
        else:
            try:
                inp = await asyncio.wait_for(queue.get(), 0.01)
            except (asyncio.QueueEmpty, asyncio.exceptions.TimeoutError):
                inp = None

        if inp is not None:
            new_gen = regen(inp)
            if new_gen is not None:
                done = False
                gen = new_gen
                reset()
                continue

        try:
            element = next(gen)
        except StopIteration:
            done = True
            continue

        yield element


@bear
async def app(page):
    q = Queue()
    debounced = ClientWrap(q, debounce=0.3, form=True)
    page["head"].print(
        H.link(rel="stylesheet", href=here.parent / "default.css")
    )
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
    area = H.div["area"](
        H.div["up"](
            H.div["column"](H.span["column-name"]("Nom")),
            H.div["column"](H.span["column-name"]("Role")),
            H.div["column"](H.span["column-name"]("Start")),
            H.div["column"](H.span["column-name"]("End")),
        ),
        H.div(id="mid-div")["mid"](),
        H.div(id="down-div")["down"](form),
    ).autoid()
    page.print(area)
    dataAuthors = {}

    def regen(event=None):
        name = None
        if event is not None:
            name = event["name"]
        if event is not None and event["$submit"] == True:
            name = None
            addAuthor(event)
        return generate(name)

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
            )
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

    with load_config(os.environ["PAPERONI_CONFIG"]) as cfg:
        with cfg.database as db:
            regen = regenerator(
                queue=q,
                regen=regen,
                reset=page["#mid-div"].clear,
            )
            async for result in regen:
                htmlAuthor(result)


ROUTES = app
