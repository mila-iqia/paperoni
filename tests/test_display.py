import json
from datetime import datetime

from sqlalchemy import select

from paperoni import model
from paperoni.db import schema as sch
from paperoni.display import (
    HTMLDisplayer,
    TerminalDisplayer,
    TerminalPrinter,
    display,
)


def test_display_paper(config_readonly, file_regression, capsys):
    pq = (
        select(sch.Paper)
        .where(
            sch.Paper.title
            == "A Remedy For Distributional Shifts Through Expected Domain Translation"
        )
        .limit(1)
    )
    with config_readonly.database as db:
        (paper,) = db.session.execute(pq)
        display(paper[0])
    file_regression.check(capsys.readouterr().out)


def test_display_researchers(config_profs, file_regression, capsys):
    yoshua = json.loads(
        config_profs.paths.database.with_suffix(".jsonl")
        .read_text()
        .split("\n")[0]
    )
    display(yoshua)
    file_regression.check(capsys.readouterr().out)


def test_display_author(file_regression, capsys):
    author = model.Author(
        name="Olivier Breuleux",
        aliases=["O Brizzle"],
        links=[model.Link(type="illuminati", link="18314")],
        quality=1.0,
        roles=[],
    )
    display(author)
    file_regression.check(capsys.readouterr().out)


def test_display_venue(file_regression, capsys):
    venue = model.Venue(
        name="Third Worldwide Illuminati Tussle",
        aliases=["TWIT"],
        date=datetime(2022, 11, 3),
        date_precision=model.DatePrecision.year,
        links=[model.Link(type="illuminati", link="1")],
        open=False,
        peer_reviewed=False,
        publisher="Elsevier",
        quality=1.0,
        series="Worldwide Illuminati Tussle",
        type=model.VenueType.conference,
        volume="3",
    )
    display(venue)
    file_regression.check(capsys.readouterr().out)


def test_TerminalPrinter(file_regression, capsys):
    with TerminalPrinter(lambda x: 2 * x) as tp:
        tp("hello")
        tp("cool")
    file_regression.check(capsys.readouterr().out)


def test_TerminalDisplayer(config_readonly, file_regression, capsys):
    with TerminalDisplayer() as td:
        pq = select(sch.Paper).limit(3)
        with config_readonly.database as db:
            for row in db.session.execute(pq):
                td(row[0])
    file_regression.check(capsys.readouterr().out)


def test_HTMLDisplayer(config_readonly, file_regression, capsys):
    with HTMLDisplayer() as hd:
        pq = select(sch.Paper).limit(3)
        with config_readonly.database as db:
            for row in db.session.execute(pq):
                hd(row[0])
    file_regression.check(capsys.readouterr().out, extension=".html")
