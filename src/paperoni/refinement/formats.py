import re
from datetime import date, datetime

from ..config import config
from ..model import (
    Author,
    DatePrecision,
    Institution,
    InstitutionCategory,
    Link,
    Paper,
    PaperAuthor,
    Release,
    Topic,
    Venue,
    VenueType,
)
from ..utils import url_to_id


async def paper_from_crossref(data):
    if not getattr(data, "author", None):
        return None
    releases = []
    if getattr(data, "event", None) or getattr(data, "container-title", None):
        date_parts = None

        if evt := getattr(data, "event", None):
            venue_name = evt["name"]
            venue_type = VenueType.conference
            if "start" in evt:
                date_parts = evt["start"]["date-parts"][0]

        if venue := getattr(data, "container-title", None):
            venue_name = venue[0]
            if data.type == "journal-article":
                venue_type = VenueType.journal
            else:
                venue_type = VenueType.conference

        if not date_parts:
            for field in (
                "published-online",
                "published-print",
                "published",
                "issued",
                "created",
            ):
                if dateholder := getattr(data, field, None):
                    date_parts = dateholder["date-parts"][0]
                    break

        short_venue_name = None

        for assertion in getattr(data, "assertion", []):
            if assertion["name"] == "conference_name":
                venue_name = assertion["value"]
            if assertion["name"] == "conference_acronym":
                short_venue_name = assertion["value"]

        precision = [
            DatePrecision.year,
            DatePrecision.month,
            DatePrecision.day,
        ][len(date_parts) - 1]
        date_parts += [1] * (3 - len(date_parts))
        release = Release(
            venue=Venue(
                aliases=[],
                name=venue_name,
                short_name=short_venue_name,
                type=venue_type,
                series=venue_name,
                links=[],
                open=False,
                peer_reviewed=False,
                publisher=None,
                date_precision=precision,
                date=date(*date_parts),
            ),
            status="published",
            pages=None,
        )
        releases = [release]

    required_keys = {"given", "family", "affiliation"}

    async def extract_affiliation(aff):
        if "id" in aff and isinstance(aff["id"], list):
            for id_entry in aff["id"]:
                if (
                    isinstance(id_entry, dict)
                    and id_entry.get("id-type") == "ROR"
                    and "id" in id_entry
                ):
                    ror_url = id_entry["id"]
                    _, ror_id = url_to_id(ror_url)
                    return await institution_from_ror(ror_id)

        else:
            return Institution(
                name=aff["name"],
                category=InstitutionCategory.unknown,
                aliases=[],
            )

    abstract = getattr(data, "abstract", None)
    if abstract:
        abstract = re.sub(r"<jats:title>.*</jats:title>", "", abstract)
        abstract = re.sub(r"</?jats:[^>]+>", "", abstract)

    return Paper(
        title=data.title[0],
        authors=[
            PaperAuthor(
                display_name=(dn := f"{author['given']} {author['family']}"),
                author=Author(name=dn),
                affiliations=[
                    await extract_affiliation(aff)
                    for aff in author["affiliation"]
                    if "name" in aff
                ],
            )
            for author in data.author
            if not (required_keys - author.keys())
        ],
        abstract=abstract,
        links=[Link(type="doi", link=data.DOI.lower())],
        topics=[],
        releases=releases,
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
        # !! COVERAGE UNKNOWN !!
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

    def parse_affiliation(aff):
        # ror = aff.select_one("institution-id[institution-id-type=ROR]")
        # links = []
        # if ror is not None:
        #     _, ror_id = url_to_id(ror.text)
        #     links.append(Link(type="ror", link=ror_id))
        nodes = aff.select("institution")
        if aff and not nodes:
            nodes = [aff]
        parts = [node.text for node in nodes]
        name = "".join(parts)
        name = re.sub(pattern="^[0-9]+", string=name, repl="")
        assert name
        return Institution(
            name=name,
            category=InstitutionCategory.unknown,
        )

    def find_affiliations(author):
        aff_nodes = [*author.select("aff")]
        aff_nodes += [
            soup.select_one(f"aff#{xaff.attrs['rid']}")
            for xaff in author.select('xref[ref-type="aff"]')
        ]
        return [parse_affiliation(aff_node) for aff_node in aff_nodes if aff_node.text]

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
                affiliations=find_affiliations(author),
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


def papers_from_arxiv(soup):
    for entry in soup.find_all("entry"):
        paper = paper_from_arxiv(entry)
        if paper is not None:
            yield paper


def paper_from_arxiv(entry):
    # Extract title
    entry_title = entry.find("title")
    if not entry_title or not entry_title.text.strip():
        return None

    entry_title_text = entry_title.text.strip()

    # Extract arxiv ID from the entry ID
    entry_id = entry.find("id")
    if not entry_id or not entry_id.text:
        return None

    arxiv_id_result = url_to_id(entry_id.text)
    if not arxiv_id_result or arxiv_id_result[0] != "arxiv":
        return None

    arxiv_id = arxiv_id_result[1]

    # Extract abstract
    summary = entry.find("summary")
    abstract = summary.text.strip() if summary and summary.text else None

    # Extract authors
    authors = []
    for author_elem in entry.find_all("author"):
        name_elem = author_elem.find("name")
        if name_elem and name_elem.text:
            author_name = name_elem.text.strip()
            authors.append(
                PaperAuthor(
                    display_name=author_name,
                    author=Author(name=author_name, aliases=[], links=[]),
                    affiliations=[],
                )
            )

    if not authors:
        return None

    # Extract published date
    published = entry.find("published")
    date_obj = None
    date_precision = DatePrecision.year
    if published and published.text:
        try:
            # Parse ISO format date: 2021-04-17T23:46:57Z
            dt = datetime.fromisoformat(published.text.replace("Z", "+00:00"))
            date_obj = dt.date()
            date_precision = DatePrecision.day
        except (ValueError, AttributeError):
            pass

    if not date_obj:
        date_obj = date(2000, 1, 1)
        date_precision = DatePrecision.year

    # Extract topics from categories
    topics = []
    for category in entry.find_all("category"):
        term = category.get("term")
        if term:
            topics.append(Topic(name=term))

    # Extract links
    links = [Link(type="arxiv", link=arxiv_id)]
    for link_elem in entry.find_all("link"):
        href = link_elem.get("href")
        rel = link_elem.get("rel")
        link_type = link_elem.get("type")
        if href:
            if rel == "alternate":
                links.append(Link(type="html", link=href))
            elif rel == "related" and link_type == "application/pdf":
                links.append(Link(type="pdf", link=href))

    # Create release (ArXiv is a preprint venue)
    releases = [
        Release(
            venue=Venue(
                name="arXiv",
                date=date_obj,
                date_precision=date_precision,
                type=VenueType.preprint,
                series="arXiv",
                aliases=[],
                links=[],
                open=True,
                peer_reviewed=False,
                publisher="Cornell University",
            ),
            status="preprint",
            pages=None,
        )
    ]

    return Paper(
        title=entry_title_text,
        abstract=abstract,
        authors=authors,
        releases=releases,
        topics=topics,
        links=links,
    )


async def institution_from_ror(ror_id):
    """
    Given a ROR ID (e.g., '025wfj672'), fetch institution info from ROR API and return an Institution object.
    """
    url = f"https://api.ror.org/v2/organizations/{ror_id}"
    data = await config.fetch.read_retry(url, format="json")

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
        "facility": InstitutionCategory.academia,
        "other": InstitutionCategory.unknown,
    }
    for t in data.get("types", []):
        if t in type_map:
            category = type_map[t]
            break

    aliases = [
        n["value"]
        for n in data.get("names", [])
        if {"alias", "label", "acronym"} & set(n.get("types", []))
    ]

    return Institution(
        name=name,
        aliases=aliases,
        category=category,
    )
