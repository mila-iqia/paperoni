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
            stmt = select(sch.Author).filter(sch.Author.name.like(f"%{name}%"))
            results = list(db.session.execute(stmt))
            mila_id = "b'vP\x1fi\xea~\xf9uE\x86\xe11E,\xad\x17'" #tmp?
            if len(results) == 0:
                author_id = "b'\xfdgk\xfd-,\xc8\xea\x03\xac\xb1+\xb2+\xcd0'"#tmp
                db.insert_author(author_id,name,0)
                db.insert_author_institution(author_id,mila_id,role,start_date,end_date)
            else:
                for (i,)  in results:
                    #Choisir quel auteur prendre...
                    db.insert_author_institution(author_id,mila_id,role,start_date,end_date)
                    print(i)
                    print(i.name)
                    print(i.roles)
            
        else:
            page["#down-div"].print(H.span(id="errormessage")("error, name, role and start date is required"))
            print("error, name, role and start date is required")

    def htmlAuthor(author):
        for i in range(len(author.roles)):
            date_start = ""
            date_end = ""
            if author.roles[i].start_date is not None:
                date_start = datetime.fromtimestamp(author.roles[i].start_date).date()
            if author.roles[i].end_date is not None:
                date_end = author.roles[i].institution_id#datetime.fromtimestamp(author.roles[i].end_date).date()

            page["#mid-div"].print(
                H.div["author-column"](
                    H.div["column-mid"](H.span(author.name)),
                    H.div["column-mid"](H.span["align-mid"](author.roles[i].role)),
                    H.div["column-mid"](H.span["align-mid"](date_start)),
                    H.div["column-mid"](H.span["align-mid"](date_end))
                    )
            )

    def generate():
        stmt = select(sch.Author)
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