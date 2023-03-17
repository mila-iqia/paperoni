"""Simple search app.
Run with `uvicorn apps.search:app`
"""

import asyncio
import os
from pathlib import Path
from datetime import datetime

from hrepr import H
from sqlalchemy import select
from starbear import ClientWrap, Queue, bear

from paperoni.config import load_config
from paperoni.db import schema as sch
from paperoni.display import html
from paperoni.utils import tag_uuid
from paperoni.model import Institution, Role, UniqueAuthor  
from hashlib import md5
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
        H.link(rel="stylesheet", href=here.parent / "paperoni" / "default.css")
    )
    area = H.div["area"](
        H.div["up"](
            H.div["column"](H.span["column-name"]("Nom")),
            H.div["column"](H.span["column-name"]("Role")),
            H.div["column"](H.span["column-name"]("Start")),
            H.div["column"](H.span["column-name"]("End"))
        ),
        H.div(id= "mid-div")["mid"](
        ),
        H.div(id= "down-div")["down"](
            H.form["addform"](
            H.input(name="name", placeholder="Name")["authorinput"],
            H.input(name="role", placeholder="Role")["authorinput"],
            "Start date",
            H.input(
                type="date", id="start", name="date-start"
            )["calender","authorinput"],
            "End date",
            H.input(
                type="date", id="end", name="date-end"
            )["calender","authorinput"],
            H.br,
            H.button("Add")["button"],
            onsubmit=debounced
        )
        )

    ).autoid()
    page.print(area)

    def regen(event=None):
        print(event)
        if event is not None:
            addAuthor(event)        
        return generate()

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
                author_id=tag_uuid(md5(name.encode("utf8")).digest(), "canonical"),
                name=name,
                aliases=[],
                affiliations=[],
                roles=[
                    uaRole
                ],
                links=[
                ],
                quality=(1.0,)
                )
            db.acquire(ua)      
        else:
            page["#down-div"].print(H.span(id="errormessage")("error, name, role and start date is required"))
            print("error, name, role and start date is required")

    def htmlAuthor(result):
        author = result.author
        date_start = ""
        date_end = ""
        if result.start_date is not None:
            date_start = datetime.fromtimestamp(result.start_date).date()
        if result.end_date is not None:
            date_end = datetime.fromtimestamp(result.end_date).date()
        page["#mid-div"].print(
            H.div["author-column"](
                H.div["column-mid"](H.span(author.name)),
                H.div["column-mid"](H.span["align-mid"](result.role)),
                H.div["column-mid"](H.span["align-mid"](date_start)),
                H.div["column-mid"](H.span["align-mid"](date_end))
                )
        )

    def generate():
        stmt = select(sch.AuthorInstitution)
        stmt = stmt.join(sch.Author)
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