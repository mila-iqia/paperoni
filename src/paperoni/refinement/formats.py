import re
from datetime import date

from ..acquire import readpage
from ..model import (
    Author,
    DatePrecision,
    Institution,
    InstitutionCategory,
    Paper,
    PaperAuthor,
    Release,
    Topic,
    Venue,
    VenueType,
)


def extract_date(txt: str) -> dict | None:
    if isinstance(txt, int):
        return {
            "date": date(txt, 1, 1),
            "date_precision": DatePrecision.year,
        }

    if not isinstance(txt, str):
        return None

    # The dash just separates the 3-letter abbreviation from the rest of the month,
    # it is split immediately after that
    months = [
        "Jan-uary",
        "Feb-ruary",
        "Mar-ch",
        "Apr-il",
        "May-",
        "Jun-e",
        "Jul-y",
        "Aug-ust",
        "Sep-tember",
        "Oct-ober",
        "Nov-ember",
        "Dec-ember",
    ]
    months = [m.split("-") for m in months]
    stems = [a.lower() for a, b in months]
    months = [(f"{a}(?:{b})?\\.?" if b else a) for a, b in months]
    month = "|".join(months)  # This is a regexp like "Jan(uary)?|Feb(ruary)?|..."

    patterns = {
        # Jan 3-Jan 7 2020
        rf"({month}) ([0-9]{{1,2}}) *- *(?:{month}) [0-9]{{1,2}}[, ]+([0-9]{{4}})": (
            "m",
            "d",
            "y",
        ),
        # Jan 3-7 2020
        rf"({month}) ([0-9]{{1,2}}) *- *[0-9]{{1,2}}[, ]+([0-9]{{4}})": (
            "m",
            "d",
            "y",
        ),
        # Jan 3 2020
        rf"({month}) ?([0-9]{{1,2}})[, ]+([0-9]{{4}})": ("m", "d", "y"),
        # 3-7 Jan 2020
        rf"([0-9]{{1,2}}) *- *[0-9]{{1,2}}[ ,]+({month})[, ]+([0-9]{{4}})": (
            "d",
            "m",
            "y",
        ),
        # 3 Jan 2020
        rf"([0-9]{{1,2}})[ ,]+({month})[, ]+([0-9]{{4}})": ("d", "m", "y"),
        # Jan 2020
        rf"({month}) +([0-9]{{4}})": ("m", "y"),
        # 2020 Jan 3
        rf"([0-9]{{4}}) ({month}) ([0-9]{{1,2}})": ("y", "m", "d"),
        # 2020 Jan
        rf"([0-9]{{4}}) ({month})": ("y", "m"),
        r"([0-9]{4})": ("y",),
    }

    for pattern, parts in patterns.items():
        if m := re.search(pattern=pattern, string=txt, flags=re.IGNORECASE):
            results = {k: m.groups()[i] for i, k in enumerate(parts)}
            precision = DatePrecision.day
            if "d" not in results:
                results.setdefault("d", 1)
                precision = DatePrecision.month
            if "m" not in results:
                results.setdefault("m", "Jan")
                precision = DatePrecision.year
            return {
                "date": date(
                    int(results["y"]),
                    stems.index(results["m"].lower()[:3]) + 1,
                    int(results["d"]),
                ),
                "date_precision": precision,
            }
    else:
        return None


def _extract_date_from_xml(node):
    if node is None:
        return None

    y = node.find("year")
    if y is not None:
        m = node.find("month")
        d = node.find("day")
        thedate = {
            "date": date(
                int(y.text),
                int((m and m.text) or 1),
                int((d and d.text) or 1),
            ),
            "date_precision": (
                DatePrecision.day
                if d
                else DatePrecision.month
                if m
                else DatePrecision.year
            ),
        }
        return thedate
    else:
        date_node = node.find("string-date")
        if date_node:
            return extract_date(date_node.text)
        else:
            return None


def paper_from_jats(soup, links):
    selectors = [
        'pub-date[pub-type="ppub"]',
        'pub-date[date-type="pub"]',
        'pub-date[date-type="pub"]',
        'pub-date[pub-type="epub"]',
        "pub-date",
    ]
    date_candidates = [
        result
        for selector in selectors
        if (result := _extract_date_from_xml(soup.select_one(selector)))
    ]
    date_candidates.sort(key=lambda x: -x["date_precision"])
    date = date_candidates and date_candidates[0]

    def find_affiliation(aff):
        # ror = soup.select_one(f"aff#{aff.attrs['rid']} institution-id[institution-id-type=ROR]")
        # links = []
        # if ror is not None:
        #     _, ror_id = url_to_id(ror.text)
        #     links.append(Link(type="ror", link=ror_id))
        nodes = soup.select(f"aff#{aff.attrs['rid']} institution")
        parts = [node.text for node in nodes]
        name = "".join(parts)
        name = re.sub(pattern="^[0-9]+", string=name, repl="")
        return Institution(
            name=name,
            category=InstitutionCategory.unknown,
        )

    abstract = soup.select_one("abstract") or ""
    if abstract:
        abstract = "\n\n".join(p.text for p in abstract.find_all("p"))

    return Paper(
        title=soup.find("article-title").text,
        authors=[
            PaperAuthor(
                display_name=(
                    dn := " ".join(
                        [
                            x.text
                            for x in [
                                *author.find_all("given-names"),
                                author.find("surname"),
                            ]
                        ]
                    )
                ),
                author=Author(
                    name=dn,
                ),
                affiliations=[
                    find_affiliation(aff) for aff in author.select('xref[ref-type="aff"]')
                ],
            )
            for author in soup.select('contrib[contrib-type="author"]')
            if author.find("surname")
        ],
        abstract=abstract,
        links=links,
        releases=[
            Release(
                venue=Venue(
                    name=(jname := soup.select_one("journal-meta journal-title").text),
                    series=jname,
                    type=VenueType.journal,
                    **date,
                    publisher=(journal := soup.select_one("journal-meta publisher-name"))
                    and journal.text,
                ),
                status="preprint" if "rxiv" in jname.lower() else "published",
                pages=None,
            )
        ],
        topics=[Topic(name=kwd.text) for kwd in soup.select("kwd-group kwd")],
    )


def institution_from_ror(ror_id):
    """
    Given a ROR ID (e.g., '025wfj672'), fetch institution info from ROR API and return an Institution object.
    """
    url = f"https://api.ror.org/v2/organizations/{ror_id}"
    data = readpage(url, format="json")

    name = None
    for n in data.get("names", []):
        if "ror_display" in n.get("types", []) or "label" in n.get("types", []):
            name = n["value"]
            break
    if not name and data.get("names"):
        name = data["names"][0]["value"]

    category = InstitutionCategory.unknown

    type_map = {
        "education": InstitutionCategory.academia,
        "funder": InstitutionCategory.unknown,
        "healthcare": InstitutionCategory.industry,
        "company": InstitutionCategory.industry,
        "archive": InstitutionCategory.academia,
        "nonprofit": InstitutionCategory.unknown,
        "government": InstitutionCategory.unknown,
        "facility": InstitutionCategory.unknown,
        "other": InstitutionCategory.unknown,
    }
    for t in data.get("types", []):
        if t in type_map:
            category = type_map[t]
            break

    return Institution(
        name=name,
        category=category,
    )
