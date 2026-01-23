import datetime
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator

import gifnoc

from ..discovery.base import Discoverer
from ..model import (
    Author,
    DatePrecision,
    Institution,
    InstitutionCategory,
    Link,
    PaperAuthor,
    Release,
    Topic,
    Venue,
    VenueType,
)
from ..model.classes import Paper
from ..utils import url_to_id


def _is_validated(paper: dict) -> bool | None:
    for flag in paper["flags"]:
        if flag["name"] == "validation":
            if flag["value"] == 1:
                return True
            elif flag["value"] == 0:
                return False
    else:
        return None


def _parse_topic(topic: dict[str, str]) -> Topic:
    return Topic(name=topic["name"])


def _parse_link(link: dict[str, str]) -> Link:
    type_link = url_to_id(link.get("url", ""))
    if type_link:
        typ, link = type_link
        return Link(type=typ, link=link)

    return Link(type=link["type"].split(".", 1)[0], link=link["link"])


def _parse_institution(institution: dict[str, str]) -> Institution:
    return Institution(
        name=institution["name"],
        category=InstitutionCategory(institution["category"]),
    )


def _parse_author(author: dict[str, str]) -> PaperAuthor:
    return PaperAuthor(
        display_name=author["author"]["name"],
        author=Author(
            name=author["author"]["name"],
            aliases=[],
            links=list(map(_parse_link, author["author"]["links"]))
            + [Link(type="paperoni_v2", link=author["author"]["author_id"])],
        ),
        affiliations=list(map(_parse_institution, author["affiliations"])),
    )


def _parse_release(release: dict[str, Any]) -> Release:
    return Release(
        venue=Venue(
            type=VenueType(release["venue"]["type"]),
            name=release["venue"]["name"],
            series=release["venue"]["series"],
            **(
                (
                    {
                        "date": datetime.datetime.fromtimestamp(
                            release["venue"]["date"]["timestamp"]
                        ).date(),
                    }
                    if release["venue"]["date"].get("timestamp", None) is not None
                    else DatePrecision.assimilate_date(release["venue"]["date"]["text"])
                )
                | {
                    "date_precision": DatePrecision(
                        release["venue"]["date"]["precision"]
                    ),
                }
            ),
            volume=release["venue"]["volume"],
            publisher=release["venue"]["publisher"],
            links=list(map(_parse_link, release["venue"]["links"])),
            peer_reviewed=release["peer_reviewed"],
        ),
        status=release["status"],
        pages=release["pages"],
    )


# TODO: complete the conversion of the paperoni v2 database to the paperoni model
# - [ ] Complete the flags information
@dataclass
class PaperoniV2(Discoverer):
    # The paperoni v2 JSON export file
    # [positional]
    # [metavar JSON]
    json: Path = field(default_factory=lambda: paperoni_v2_json)

    async def query(
        self,
        # Embed the paperoni v2 paper's JSON in the Paper info dictionary
        embed: bool = False,
    ) -> AsyncGenerator[Paper, None]:
        """Query the paperoni v2 database"""
        with self.json.open() as f:
            papers = json.load(f)

        for paper in papers:
            yield Paper(
                title=paper["title"],
                abstract=paper["abstract"],
                authors=list(map(_parse_author, paper["authors"])),
                releases=list(map(_parse_release, paper["releases"])),
                topics=list(map(_parse_topic, paper["topics"])),
                links=list(map(_parse_link, paper["links"])),
                flags=set(
                    (["validated"] if _is_validated(paper) else [])
                    + (["~validated"] if _is_validated(paper) is False else [])
                ),
                key=f"paperoni_v2:{paper['paper_id']}",
                info={"discovered_by": {"paperoni_v2": paper["paper_id"]}}
                | ({"v2": paper} if embed else {}),
                score=10.0 if _is_validated(paper) else 0.0,
                version=datetime.datetime.now(),
            )


paperoni_v2_json: Path | None = gifnoc.define(
    "paperoni.discovery.v2.data", Path | None, defaults=None
)
