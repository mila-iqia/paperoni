from datetime import datetime
import json

from coleo import Option, auto_cli

from paperoni.config import config, configure
from paperoni.model import DatePrecision, from_dict
from paperoni.utils import canonicalize_links

mag_types = {
    1: "html",
    2: "patent",
    3: "pdf",
    12: "xml",
    99: "unknown",
    999: "unknown_",
}


def process_paper(paper):
    if paper is False:
        return None

    if "J" in paper:
        j = paper["J"]
        detail = paper.get("V", None) or paper["D"]
        lnk = f'{j["JId"]}/{detail}'
        venue = {
            "type": "journal",
            "name": paper.get("BV", None) or j["JN"],
            "series": j["JN"],
            "links": [{"type": "mag", "link": lnk}],
            "quality": [0.5],
        }
    elif "C" in paper:
        c = paper["C"]
        lnk = f'{c["CId"]}/{paper["Y"]}'
        venue = {
            "type": "conference",
            "name": paper.get("BV", None) or c["CN"],
            "series": c["CN"],
            "links": [{"type": "mag", "link": lnk}],
            "quality": [0.5],
        }
    else:
        venue = {
            "type": "unknown",
            "name": (name := paper.get("BV", None) or paper.get("VFN", None) or "n/a"),
            "series": name,
            "links": [],
            "quality": [0.0],
        }

    venue.update(
        {
            "series": venue["name"],
            **DatePrecision.assimilate_date(paper["D"]),
            "volume": paper.get("V", None),
            "publisher": paper.get("PB", None),
            "aliases": [],
        }
    )

    release = {
        "venue": venue,
        "status": "published",
        "pages": None,
    }

    authors = {}
    for auth in paper["AA"]:
        auid = auth["AuId"]
        authors.setdefault(
            auid,
            {
                "affiliations": [],
                "author": {
                    "name": auth["DAuN"],
                    "links": [{"type": "mag", "link": auid}],
                    "affiliations": [],
                    "aliases": [],
                    "roles": [],
                    "quality": [0.5],
                },
            },
        )
        authors[auid]["affiliations"].append(
            {
                "name": auth["DAfN"],
                "category": "unknown",
                "aliases": [],
            }
        )

    result = {
        "__version__": 1,
        "__type__": "Paper",
        "__source__": "mag",
        "title": paper["DN"],
        "abstract": paper["abstract"],
        "links": [
            {"type": "mag", "link": paper["Id"]},
            *canonicalize_links(
                {"type": mag_types[entry.get("Ty", 99)], "link": entry["U"]}
                for entry in paper.get("S", [])
            ),
        ],
        "authors": list(authors.values()),
        "releases": [
            release,
        ],
        "topics": [{"name": f["FN"]} for f in paper.get("F", [])],
        "citation_count": None,  # The counts are stale anyway
        "quality": [0.5],
    }
    return result


def mag_papers(json_db):
    data = json.load(open(json_db))
    yield {
        "__type__": "Meta",
        "scraper": "mag",
        "date": datetime.now(),
    }
    for _, paper in data.items():
        result = process_paper(paper)
        if result is not None:
            yield result


def show():
    from paperoni.utils import display

    # [positional]
    filename: Option

    for paper in mag_papers(filename):
        print("=" * 80)
        display(paper)


def store():
    from paperoni.db.database import Database

    # [positional]
    filename: Option

    configure("config.yaml", tag="mag")
    db = Database(config.database_file)
    db.import_all([from_dict(paper) for paper in mag_papers(filename)])


if __name__ == "__main__":
    auto_cli(
        {
            "show": show,
            "store": store,
        }
    )
