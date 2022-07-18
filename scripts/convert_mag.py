import json
import sys

from coleo import auto_cli

from paperoni.config import config, configure
from paperoni.sources.model import DatePrecision, from_dict
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
        venue = {
            "type": "journal",
            "name": paper.get("BV", None) or paper["J"]["JN"],
            "links": [{"type": "mag", "link": paper["J"]["JId"]}],
        }
    elif "C" in paper:
        venue = {
            "type": "conference",
            "name": paper.get("BV", None) or paper["C"]["CN"],
            "links": [{"type": "mag", "link": paper["C"]["CId"]}],
        }
    else:
        venue = {
            "type": "unknown",
            "name": paper.get("BV", None) or paper.get("VFN", None) or "n/a",
            "links": [],
        }

    release = {
        "venue": venue,
        **DatePrecision.assimilate_date(paper["D"]),
        "volume": paper.get("V", None),
        "publisher": paper.get("PB", None),
    }

    authors = {}
    for auth in paper["AA"]:
        auid = auth["AuId"]
        authors.setdefault(
            auid,
            {
                "name": auth["DAuN"],
                "links": [{"type": "mag", "link": auid}],
                "affiliations": [],
                "aliases": [],
                "roles": [],
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
        "scrapers": ["mag"],
        "citation_count": paper["CC"],
    }
    return result


def mag_papers(json_db):
    data = json.load(open(json_db))
    for _, paper in data.items():
        result = process_paper(paper)
        if result is not None:
            yield result


def show():
    from paperoni.utils import format_term_long as ft

    for paper in mag_papers(sys.argv[1]):
        print("=" * 80)
        ft(from_dict(paper))


def store():
    from paperoni.db.database import Database
    from paperoni.utils import format_term_long as ft

    configure("config.yaml")
    db = Database(config.database_file)
    db.import_all([from_dict(paper) for paper in mag_papers(sys.argv[1])])


if __name__ == "__main__":
    auto_cli(
        {
            "show": show,
            "store": store,
        }
    )
