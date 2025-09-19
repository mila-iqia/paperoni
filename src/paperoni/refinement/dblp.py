import re
from datetime import date
from typing import Literal

from ..config import config
from ..model import (
    Author,
    DatePrecision,
    Link,
    Paper,
    PaperAuthor,
    Release,
    Venue,
    VenueType,
)
from .fetch import register_fetch


def _clean_author_name(name):
    return re.sub(r"\s*\d+$", "", name)


def _author_links(author_span):
    links = [Link(type="dblp", link=author_span.text)]
    if orcid := author_span.attrs.get("orcid"):
        links.append(Link(type="orcid", link=orcid))
    return links


@register_fetch
def dblp(type: Literal["dblp"], link: str):
    data = config.fetch.read(f"https://dblp.uni-trier.de/rec/{link}.xml", format="xml")
    ee = data.find("ee")
    extra_links = []
    if ee and ee.text.startswith("https://doi.org/"):
        doi = ee.text.replace("https://doi.org/", "")
        extra_links = [Link(type="doi", link=doi.lower())]
    elif ee:
        extra_links = [Link(type="html", link=ee.text)]

    if m := re.match(r".*/corr/abs-(\d+)-(\d+)", link):
        arxiv_id = f"{m.group(1)}.{m.group(2)}"
        extra_links.append(Link(type="arxiv", link=arxiv_id))
        jname = "arXiv"
        status = "preprint"
    else:
        jname = (data.find("booktitle") or data.find("journal")).text
        status = "published"

    return Paper(
        title=data.find("title").text,
        abstract=None,
        authors=[
            PaperAuthor(
                display_name=(name := _clean_author_name(author.text)),
                author=Author(
                    name=name,
                    links=_author_links(author),
                ),
                affiliations=[],
            )
            for author in data.select("author")
        ],
        links=[Link(type=type, link=link), *extra_links],
        releases=[
            Release(
                venue=Venue(
                    name=jname,
                    series=jname,
                    type=VenueType.journal,
                    date=date(year=int(data.find("year").text), month=1, day=1),
                    date_precision=DatePrecision.year,
                    publisher=None,
                ),
                status=status,
                pages=(pg := data.find("pages")) and pg.text,
            )
        ],
        topics=[],
    )
