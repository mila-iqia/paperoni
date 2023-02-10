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
        title = "neural" if event is None else event["value"]
        return generate(title)

    def generate(title):
        stmt = select(sch.Paper)
        stmt = stmt.filter(sch.Paper.title.like(f"%{title}%"))
        results = list(db.session.execute(stmt))
        for (r,) in results:
            if not hasPaperValidation(r):
                yield r

    def validateButton(paper,val):
        db.insertFlag(paper, "validation", val)
        deleteid = "#p"+paper.paper_id.hex()
        page[deleteid].delete()

    def hasPaperValidation(paper):
        return db.hasPaperValidation(paper)

    def getFlags(paper):
        flagTab = []
        for flag in db.getAllFlags(paper):
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
                if not hasPaperValidation(result):
                    div = html(result)
                    divFlags = getFlags(result)
                    valDiv = H.div["validationDiv"](
                            div,
                            H.button["button"]("Validate",
                            onclick=(lambda event, paper=result:validateButton(paper,1))),
                            H.button["button","invalidate"]("Invalidate",
                            onclick=(lambda event, paper=result:validateButton(paper,0))),
                            divFlags
                    )(id="p"+result.paper_id.hex())
                    page[area].print(
                        valDiv
                    )
                    
