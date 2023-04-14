"""Simple validation app.
Run with `uvicorn apps.validation:app`
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path

from hrepr import H
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
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
    area = H.div["area"]().autoid()
    page.print(H.span("Validation"))
    page.print(area)

    author_name = "Amin Emad"

    def regen(event=None):
        if event is not None:
            title = event["title"]
            author = event["author"]
            date_start = event["date-start"]
            date_end = event["date-end"]
            return generate(title, author, date_start, date_end)
        return generate()

    def generate(title=None, author=None, date_start=None, date_end=None):
        stmt = select(sch.Paper)
        stmt = (
                stmt.join(sch.Paper.paper_author)
                .join(sch.PaperAuthor.author)
                .filter(sch.Author.name.like(f"%{author_name}%"))
            )
        if not all(
            val is "" or val is None
            for val in [title, author, date_start, date_end]
        ):
            stmt = (
                stmt.join(sch.Paper.paper_author)
                .join(sch.PaperAuthor.author)
                .filter(sch.Author.name.like(f"%{author_name}%"))
            )
        try:
            results = list(db.session.execute(stmt))
            for (r,) in results:
                yield r
        except Exception as e:
            print("Error : ", e)

    def search(title, author, date_start, date_end):
        stmt = select(sch.Paper)
        # Selecting from the title
        if title is not None and title != "":
            stmt = select(sch.Paper).filter(sch.Paper.title.like(f"%{title}%"))
        # Selecting from author
        if author is not None and author != "":
            stmt = (
                stmt.join(sch.Paper.paper_author)
                .join(sch.PaperAuthor.author)
                .filter(sch.Author.name.like(f"%{author}%"))
            )

        # Selecting from date
        # Joining the tables if any of the dates are set
        if (date_start is not None and date_start != "") or (
            date_end is not None and date_end != ""
        ):
            stmt = stmt.join(sch.Paper.release).join(sch.Release.venue)

        # Filtering for the dates
        if date_start is not None and date_start != "":
            date_start_stamp = int(
                datetime(*map(int, date_start.split("-"))).timestamp()
            )
            stmt = stmt.filter(sch.Venue.date >= date_start_stamp)
        if date_end is not None and date_end != "":
            date_end_stamp = int(
                datetime(*map(int, date_end.split("-"))).timestamp()
            )
            stmt = stmt.filter(sch.Venue.date <= date_end_stamp)

        return stmt

    with load_config(os.environ["PAPERONI_CONFIG"]) as cfg:
        with cfg.database as db:
            regen = regenerator(
                queue=q,
                regen=regen,
                reset=page[area].clear,
            )
            async for result in regen:
                div = html(result)
                valDiv = H.div["validationDiv"](
                        div)
                page[area].print(valDiv)
