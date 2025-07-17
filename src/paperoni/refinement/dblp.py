from datetime import date
from typing import Literal

from ..acquire import readpage
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


@register_fetch
def dblp(type: Literal["dblp"], link: str):
    if "/corr/" in link:
        return None

    data = readpage(f"https://dblp.uni-trier.de/rec/{link}.xml", format="xml")
    ee = data.find("ee")
    extra_links = []
    if ee and ee.text.startswith("https://doi.org/"):
        doi = ee.text.replace("https://doi.org/", "")
        extra_links = [Link(type="doi", link=doi)]
    elif ee:
        extra_links = [Link(type="html", link=ee.text)]
    return Paper(
        title=data.find("title").text,
        abstract="",
        authors=[
            PaperAuthor(
                display_name=author.text,
                author=Author(
                    name=author.text,
                    links=(
                        [Link(type="orcid", link=orcid)]
                        if (orcid := author.attrs.get("orcid", None))
                        else []
                    ),
                ),
                affiliations=[],
            )
            for author in data.select("author")
        ],
        links=[Link(type=type, link=link), *extra_links],
        releases=[
            Release(
                venue=Venue(
                    name=(jname := (data.find("booktitle") or data.find("journal")).text),
                    series=jname,
                    type=VenueType.journal,
                    date=date(year=int(data.find("year").text), month=1, day=1),
                    date_precision=DatePrecision.year,
                    publisher=None,
                ),
                status="published",
                pages=(pg := data.find("pages")) and pg.text,
            )
        ],
        topics=[],
    )
