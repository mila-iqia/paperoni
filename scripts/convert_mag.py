import sys
import json
from paperoni.sources.model import from_dict
from paperoni.utils import url_to_id


mag_types = {
    1: "html",
    2: "patent",
    3: "pdf",
    12: "xml",
    99: "unknown",
    999: "unknown_",
}


def process_paper(paper):
    def _make_link(link):
        typ = mag_types[link.get("Ty", 99)]
        lnk = link["U"]
        return url_to_id(lnk) or (typ, lnk)

    def _make_links(links):
        links = {_make_link(link) for link in links}
        return [{"type": typ, "link": lnk} for typ, lnk in links]

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
        "date": f"{paper['D']} 00:00:00",
        "date_precision": 86400,
        "volume": paper.get("V", None),
        "publisher": paper.get("PB", None),
    }

    authors = {}
    for auth in paper["AA"]:
        auid = auth["AuId"]
        authors.setdefault(auid, {
            "name": auth["DAuN"],
            "links": [{"type": "mag", "link": auid}],
            "affiliations": [],
        })
        authors[auid]["affiliations"].append({
            "name": auth["DAfN"],
        })

    result = {
        "__version__": 1,
        "__type__": "Paper",
        "__source__": "mag",
        "title": paper["DN"],
        "abstract": paper["abstract"],
        "links": [
            {"type": "mag", "link": paper["Id"]},
            *_make_links(paper.get("S", []))
        ],
        "authors": list(authors.values()),
        "releases": [
            release,
        ],
        "topics": [
            {"name": f["FN"]}
            for f in paper.get("F", [])
        ],
        "citation_count": paper["CC"],
    }
    return result


def mag_papers(json_db):
    data = json.load(open(json_db))
    for _, paper in data.items():
        result = process_paper(paper)
        if result is not None:
            yield result


def main():
    from paperoni.utils import format_term_long as ft
    for paper in mag_papers(sys.argv[1]):
        print("=" * 80)
        ft(from_dict(paper))
        break
