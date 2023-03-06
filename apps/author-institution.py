"""Simple search app.
Run with `uvicorn apps.search:app`
"""

import asyncio
import os
from pathlib import Path

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
    debounced = ClientWrap(q, debounce=0.3)
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
        H.div["mid"],
        H.div["down"]

    ).autoid()
    page.print(area)

    def regen(event=None):
        title = "neural" if event is None else event["value"]
        return generate(title)
    
    def htmlAuthor(author):
        #tab = []
        #if len(author.roles) > 0:
        #    for role in author.roles:
        #        tab.append(H.span["author-name"](role.role))
        #    return H.div["author"](
        #        author.name,
        #        tab
        #    )
        #
        #return None      
        #div = []
        #div.append(H.div["up"])
        #div.append(H.div["mid"])
        #div.append(H.div["down"])
        return None

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
        print(db.session.execute(stmt))
        results = list(db.session.execute(stmt))
        for (r,) in results:
            yield r

    with load_config(os.environ["PAPERONI_CONFIG"]) as cfg:
        with cfg.database as db:
            regen = regenerator(
                queue=q,
                regen=regen,
                reset=page[area].clear,
            )
            async for result in regen:
                print(result)
                div = htmlAuthor(result)
                page[area].print(div)
                #page[area].print(H.br)