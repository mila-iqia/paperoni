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
        H.div["down"](
            H.form["addform"](
            H.input(name="name", placeholder="Name")["authorinput"],
            H.input(name="role", placeholder="Role")["authorinput"],
            "Start date",
            H.input(
                type="date", id="start", name="date-start"
            )["calender","authorinput"],
            "End date",
            H.input(
                type="date", id="start", name="date-end"
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
        title = "neural" if event is None else event["name"]
        return generate(title)
    
    def htmlAuthor(author):
        for i in range(len(author.roles)):
            date_start = ""
            date_end = ""
            if author.roles[i].start_date is not None:
                date_start = datetime.fromtimestamp(author.roles[i].start_date).date()
            if author.roles[i].end_date is not None:
                date_end = datetime.fromtimestamp(author.roles[i].end_date).date()

            page["#mid-div"].print(
                H.div["author-column"](
                    H.div["column-mid"](H.span(author.name)),
                    H.div["column-mid"](H.span["align-mid"](author.roles[i].role)),
                    H.div["column-mid"](H.span["align-mid"](date_start)),
                    H.div["column-mid"](H.span["align-mid"](date_end))
                    )
            )

    def generate(title):
        stmt = select(sch.Author)
        #stmt = stmt.filter(sch.AuthorInstitution.role.like(f"%{title}%"))
        #stmt = stmt.join(sch.Author.author_id)
        #stmt = (
        #           stmt.join(sch.Author).join(
        #               sch.AuthorInstitution
        #           )
        #           .filter(sch.Author.name.like(f"")))
        #       )
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
                if len(result.roles) > 0:
                    htmlAuthor(result)
                    #page[area].print(div)
                #page[area].print(H.br)