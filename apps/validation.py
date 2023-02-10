"""Simple validation app.
Run with `uvicorn apps.validation:app`
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
    area = H.div["area"]().autoid()
    page.print(area)

    def regen(event=None):
        title = None if event is None else event["value"]
        return generate(title)

    def generate(title):
        stmt = select(sch.Paper)
        if title is not None and not "":
            stmt = stmt.filter(sch.Paper.title.like(f"%{title}%"))
        results = list(db.session.execute(stmt))
        for (r,) in results:
                yield r

    def validate_button(paper,val):
        db.insert_flag(paper, "validation", val)
        deleteid = "#p"+paper.paper_id.hex()
        page[deleteid].delete()

    def has_paper_validation(paper):
        return db.has_flag(paper,"validation")

    def get_flags(paper):
        flagTab = []
        for flag in paper.paper_flag:
            flagTab.append(H.div["flag"](str(flag.flag_name)))
        return flagTab

    with load_config(os.environ["PAPERONI_CONFIG"]) as cfg:
        with cfg.database as db:
            regen = regenerator(
                queue=q,
                regen=regen,
                reset=page[area].clear,
            )
            async for result in regen:
                if not has_paper_validation(result):
                    div = html(result)
                    divFlags = get_flags(result)
                    valDiv = H.div["validationDiv"](
                            div,
                            H.button["button"]("Validate",
                            onclick=(lambda event, paper=result:validate_button(paper,1))),
                            H.button["button","invalidate"]("Invalidate",
                            onclick=(lambda event, paper=result:validate_button(paper,0))),
                            divFlags
                    )(id="p"+result.paper_id.hex())
                    page[area].print(
                        valDiv
                    )
                    
