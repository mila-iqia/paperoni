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

from .render import paper_html

from .common import search_interface

here = Path(__file__).parent


async def regenerator(queue, regen, reset, db):
    gen = regen(db=db)
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
            new_gen = regen(inp, db)
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
    """Search for papers."""
    q = Queue()
    debounced = ClientWrap(q, debounce=0.3, form=True)
    page["head"].print(H.link(rel="stylesheet", href=here / "app-style.css"))
    area = H.div["area"]().autoid()
    page.print(
        H.form(
            H.input(name="title", placeholder="Title", oninput=debounced),
            H.input(name="author", placeholder="Author", oninput=debounced),
            H.input(name="venue", placeholder="Venue", oninput=debounced),
            H.br,
            "Start Date",
            H.input(
                type="date", id="start", name="date-start", oninput=debounced
            )["calendar"],
            H.br,
            "End Date",
            H.input(
                type="date", id="start", name="date-end", oninput=debounced
            )["calendar"],
        ),
    )
    page.print(area)

    with load_config(os.environ["PAPERONI_CONFIG"]) as cfg:
        with cfg.database as db:
            regen = regenerator(
                queue=q,
                regen=search_interface,
                reset=page[area].clear,
                db=db,
            )
            async for result in regen:
                div = paper_html(result)
                page[area].print(div)


ROUTES = app
