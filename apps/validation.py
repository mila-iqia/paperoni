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
            if not isPaperFlagged(r):
                yield r

    def validate(paper):
        db.insertFlag(paper, 1)
        deleteid = "#p"+paper.paper_id.hex()
        page[deleteid].delete()
    
    def invalidate(paper):
        db.insertFlag(paper, 0)
        deleteid = "#p"+paper.paper_id.hex()
        page[deleteid].delete()

    def isPaperFlagged(paper):
        return db.isPaperFlagged(paper)

    with load_config(os.environ["PAPERONI_CONFIG"]) as cfg:
        with cfg.database as db:
            regen = regenerator(
                queue=q,
                regen=regen,
                reset=page[area].clear,
            )
            async for result in regen:
                if not isPaperFlagged(result):
                    div = html(result)
                    valDiv = H.div["validationDiv"](
                            div,
                            H.button["button"]("Validate",
                            onclick=(lambda event, paper=result:validate(paper))),
                            H.button["button","invalidate"]("Invalidate",
                            onclick=(lambda event, paper=result:invalidate(paper)))
                    )(id="p"+result.paper_id.hex())
                    page[area].print(
                        valDiv
                    )
                    
