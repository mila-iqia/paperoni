"""Simple validation app.
Run with `uvicorn apps.validation:app`
"""

import asyncio
import os
from datetime import datetime
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
    """Validate papers."""
    seeFlagged = False
    q = Queue()
    debounced = ClientWrap(q, debounce=0.3, form=True)
    page["head"].print(H.link(rel="stylesheet", href=here / "app-style.css"))
    area = H.div["area"]().autoid()

    async def toggleSeeFlagged(form=None):
        nonlocal seeFlagged
        seeFlagged = not seeFlagged
        await q.put(form)

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
            H.div(id="seeFlagged")["seeFlagged"](
                "See Flagged Papers",
                H.input(
                    type="checkbox",
                    id="seeFlagged",
                    name="seeFlagged",
                    value="seeFlagged",
                    oninput=ClientWrap(toggleSeeFlagged, form=True),
                ),
            ),
        ),
    )
    page.print(area)

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
                paper_html(paper),
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
            seeFlagged = False
            regen = regenerator(
                queue=q,
                regen=search_interface,
                reset=page[area].clear,
                db=db,
            )
            async for result in regen:
                if seeFlagged:
                    if has_paper_validation(result):
                        div = paper_html(result)
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
                        div = paper_html(result)
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
