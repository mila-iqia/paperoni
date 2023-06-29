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
    seeFlagged = False
    q = Queue()
    debounced = ClientWrap(q, debounce=0.3, form=True)
    page["head"].print(
        H.link(rel="stylesheet", href=here.parent / "paperoni" / "default.css")
    )
    area = H.div["area"]().autoid()
    page.print(
        H.form(
            H.input(name="title", placeholder="Title", oninput=debounced),
            H.input(name="author", placeholder="Author", oninput=debounced),
            H.br,
            "Start Date",
            H.input(
                type="date", id="start", name="date-start", oninput=debounced
            )["calender"],
            H.br,
            "End Date",
            H.input(
                type="date", id="start", name="date-end", oninput=debounced
            )["calender"],
            H.div(id="seeFlagged")["seeFlagged"](
                "See Flagged Papers",
                H.input(
                    type="checkbox",
                    id="seeFlasgged",
                    name="seeFlagged",
                    value="seeFlagged",
                    oninput=debounced,
                ),
            ),
        )
    )
    page.print(area)

    def regen(event=None):
        if event is not None and event:
            nonlocal seeFlagged
            seeFlagged = event["seeFlagged"]
            title = event["title"]
            author = event["author"]
            date_start = event["date-start"]
            date_end = event["date-end"]
            return generate(title, author, date_start, date_end)
        return generate()

    def generate(title=None, author=None, date_start=None, date_end=None):
        stmt = select(sch.Paper)
        if not all(
            val == "" or val is None
            for val in [title, author, date_start, date_end]
        ):
            stmt = search(title, author, date_start, date_end)
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

    def getChangedButton(result):
        for flag in result.paper_flag:
            if flag.flag_name == "validation" and flag.flag == 1:
                return H.button["button", "invalidate"](
                    "Invalidate",
                    onclick=(
                        lambda event, paper=result: changeValidation(paper, 0)
                    ),
                )
            elif flag.flag_name == "validation" and flag.flag == 0:
                return H.button["button"](
                    "Validate",
                    onclick=(
                        lambda event, paper=result: changeValidation(paper, 1)
                    ),
                )
        return None

    def changeValidation(paper, val):
        db.remove_flags(paper, "validation")
        db.insert_flag(paper, "validation", val)
        deleteid = "#p" + paper.paper_id.hex()
        page[deleteid].clear()
        # Update the paper html
        page[deleteid].print(
            H.div(
                html(paper),
                H.button["button"](
                    "Undo",
                    onclick=(lambda event, paper=paper: unValidate(paper)),
                ),
                getChangedButton(paper),
                get_flags(paper),
            )
        )

    def validate_button(paper, val):
        db.insert_flag(paper, "validation", val)
        deleteid = "#p" + paper.paper_id.hex()
        page[deleteid].delete()

    def unValidate(paper):
        db.remove_flags(paper, "validation")
        deleteid = "#p" + paper.paper_id.hex()
        page[deleteid].delete()

    def has_paper_validation(result):
        if type(result).__name__ == "Paper":
            return db.has_flag(result, "validation")
        return False

    def get_flags(paper):
        flagTab = []
        for flag in paper.paper_flag:
            if flag.flag == 1:
                flagTab.append(
                    H.div["flag"](str(flag.flag_name) + " : Validated")
                )
            else:
                flagTab.append(
                    H.div["flag"](str(flag.flag_name) + " : Invalidated")
                )
        return flagTab

    with load_config(os.environ["PAPERONI_CONFIG"]) as cfg:
        with cfg.database as db:
            regen = regenerator(
                queue=q,
                regen=regen,
                reset=page[area].clear,
            )
            async for result in regen:
                if seeFlagged:
                    if has_paper_validation(result):
                        div = html(result)
                        divFlags = get_flags(result)
                        buttonChange = getChangedButton(result)
                        valDiv = H.div["validationDiv"](
                            div,
                            H.button["button"](
                                "Undo",
                                onclick=(
                                    lambda event, paper=result: unValidate(
                                        paper
                                    )
                                ),
                            ),
                            buttonChange,
                            divFlags,
                        )(id="p" + result.paper_id.hex())
                        page[area].print(valDiv)
                else:
                    if not has_paper_validation(result):
                        div = html(result)
                        divFlags = get_flags(result)
                        valDiv = H.div["validationDiv"](
                            div,
                            H.button["button"](
                                "Validate",
                                onclick=(
                                    lambda event, paper=result: validate_button(
                                        paper, 1
                                    )
                                ),
                            ),
                            H.button["button", "invalidate"](
                                "Invalidate",
                                onclick=(
                                    lambda event, paper=result: validate_button(
                                        paper, 0
                                    )
                                ),
                            ),
                            divFlags,
                        )(id="p" + result.paper_id.hex())
                        page[area].print(valDiv)


ROUTES = app
