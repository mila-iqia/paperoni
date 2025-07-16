import re
from datetime import date
from types import SimpleNamespace
from typing import Literal

from ovld.dependent import StartsWith
from requests import HTTPError

from ..acquire import readpage
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
from .fetch import register_fetch
from .formats import institution_from_ror, paper_from_jats


@register_fetch
def crossref(type: Literal["doi"], link: str):
    """Fetch from CrossRef."""

    doi = link
    if "arXiv" in doi:  # pragma: no cover
        # We know it's not indexed here
        return None

    try:
        data = readpage(f"https://api.crossref.org/v1/works/{doi}", format="json")
    except HTTPError as exc:  # pragma: no cover
        if exc.response.status_code == 404:
            return None
        else:
            raise

    if data["status"] != "ok":  # pragma: no cover
        raise Exception("Request failed", data)

    data = SimpleNamespace(**data["message"])

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

    def extract_affiliation(aff):
        if "id" in aff and isinstance(aff["id"], list):
            for id_entry in aff["id"]:
                if (
                    isinstance(id_entry, dict)
                    and id_entry.get("id-type") == "ROR"
                    and "id" in id_entry
                ):
                    ror_url = id_entry["id"]
                    _, ror_id = url_to_id(ror_url)
                    return institution_from_ror(ror_id)

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
                    extract_affiliation(aff)
                    for aff in author["affiliation"]
                    if "name" in aff
                ],
            )
            for author in data.author
            if not (required_keys - author.keys())
        ],
        abstract=abstract,
        links=[Link(type="doi", link=doi)],
        topics=[],
        releases=releases,
    )


@register_fetch
def datacite(type: Literal["doi"], link: str):
    """
    Refine using DataCite.

    More info:
    API call tutorial: https://support.datacite.org/docs/api-get-doi
    API call reference: https://support.datacite.org/reference/get_dois-id
    DataCite metadata properties: https://datacite-metadata-schema.readthedocs.io/en/4.5/properties/
    """
    doi = link

    try:
        json_data = readpage(
            f"https://api.datacite.org/dois/{doi}?publisher=true&affiliation=true",
            format="json",
        )
    except HTTPError as exc:  # pragma: no cover
        if exc.response.status_code == 404:
            return None
        else:
            raise

    if "errors" in json_data:  # pragma: no cover
        raise Exception("Could not fetch from datacite", json_data)

    # Mapping to convert DataCite resource type to Paperoni venue type.
    # May be improved.
    item_type_to_venue_type = {
        "Audiovisual": VenueType.unknown,
        "Book": VenueType.book,
        "BookChapter": VenueType.book,
        "Collection": VenueType.unknown,
        "ComputationalNotebook": VenueType.unknown,
        "ConferencePaper": VenueType.conference,
        "ConferenceProceeding": VenueType.conference,
        "DataPaper": VenueType.unknown,
        "Dataset": VenueType.unknown,
        "Dissertation": VenueType.unknown,
        "Event": VenueType.unknown,
        "Image": VenueType.unknown,
        "Instrument": VenueType.unknown,
        "InteractiveResource": VenueType.unknown,
        "Journal": VenueType.journal,
        "JournalArticle": VenueType.journal,
        "Model": VenueType.unknown,
        "OutputManagementPlan": VenueType.unknown,
        "PeerReview": VenueType.review,
        "PhysicalObject": VenueType.unknown,
        "Preprint": VenueType.preprint,
        "Report": VenueType.unknown,
        "Service": VenueType.unknown,
        "Software": VenueType.unknown,
        "Sound": VenueType.unknown,
        "Standard": VenueType.unknown,
        "StudyRegistration": VenueType.unknown,
        "Text": VenueType.unknown,
        "Workflow": VenueType.unknown,
        "Other": VenueType.unknown,
    }

    raw_paper = SimpleNamespace(**json_data["data"]["attributes"])

    # Get paper abstract
    abstract = None
    for desc in raw_paper.descriptions:
        if desc["descriptionType"] == "Abstract":
            abstract = desc["description"]
            break

    # Get paper date, used for paper default release
    for date_info in raw_paper.dates:
        if date_info["dateType"] == "Available":  # Available, or Issued ?
            date_string = date_info["date"]
            date_pieces = date_string.split("-")
            if len(date_pieces) == 1:
                # !! COVERAGE UNKNOWN !!
                date_available = date(year=int(date_pieces[0]), month=1, day=1)
                date_precision = DatePrecision.year
            elif len(date_pieces) == 2:
                date_available = date(
                    year=int(date_pieces[0]), month=int(date_pieces[1]), day=1
                )
                date_precision = DatePrecision.month
            else:
                # !! COVERAGE UNKNOWN !!
                date_available = date.fromisoformat(date_string)
                date_precision = DatePrecision.day
            break
    else:
        # !! COVERAGE UNKNOWN !!
        date_available = date(year=raw_paper.publicationYear, month=1, day=1)
        date_precision = DatePrecision.year

    # Try to get paper default release
    releases = [
        Release(
            venue=Venue(
                type=item_type_to_venue_type[raw_paper.types["resourceTypeGeneral"]],
                name=raw_paper.publisher["name"],
                date=date_available,
                date_precision=date_precision,
                series="",
                aliases=[],
                links=[],
            ),
            status="published",
            pages=None,
        )
    ]
    # Try to get more paper releases
    for related_item in raw_paper.relatedItems:
        # !! COVERAGE UNKNOWN !!
        if (
            related_item["relationType"] == "IsPublishedIn"
            and related_item["relatedItemType"] in item_type_to_venue_type
        ):
            releases.append(
                Release(
                    venue=Venue(
                        type=item_type_to_venue_type[related_item["relatedItemType"]],
                        name=related_item["titles"][0]["title"],
                        series=related_item["issue"],
                        date=date(
                            year=int(related_item["publicationYear"]),
                            month=1,
                            day=1,
                        ),
                        date_precision=DatePrecision.year,
                        volume=related_item["volume"],
                        publisher=related_item["publisher"],
                    ),
                    status="published",
                    pages=f"{related_item['firstPage']}-{related_item['lastPage']}",
                )
            )

    # Get paper default links
    links = [Link(type="doi", link=doi)]
    if raw_paper.url:
        links.append(Link(type="url", link=raw_paper.url))
    for content_url in raw_paper.contentUrl or ():
        # !! COVERAGE UNKNOWN !!
        links.append(Link(type="contentUrl", link=content_url))
    # Try to get more paper links
    for related_identifier in raw_paper.relatedIdentifiers:
        identifier_type = related_identifier["relatedIdentifierType"]
        relation_type = related_identifier["relationType"]
        identifier = related_identifier["relatedIdentifier"]
        # Available identifier types:
        # ARK arXiv bibcode DOI EAN13 EISSN Handle IGSN ISBN ISSN ISTC LISSN LSID PMID PURL UPC URL URN w3id
        if identifier_type in {"ARK", "arXiv", "DOI", "PURL", "URL", "w3id"}:
            links.append(Link(type=f"{relation_type}.{identifier_type}", link=identifier))

    return Paper(
        title=raw_paper.titles[0]["title"],
        abstract=abstract,
        authors=[
            PaperAuthor(
                display_name=(dn := f"{creator['givenName']} {creator['familyName']}"),
                author=Author(
                    name=dn,
                    aliases=[],
                    links=[],
                ),
                affiliations=[
                    Institution(
                        name=affiliation["name"],
                        category=InstitutionCategory.unknown,
                        aliases=[],
                    )
                    for affiliation in creator["affiliation"]
                ],
            )
            for creator in raw_paper.creators
            if creator["nameType"] == "Personal"
        ],
        releases=releases,
        topics=[Topic(name=subject["subject"]) for subject in raw_paper.subjects],
        links=links,
    )


@register_fetch
def biorxiv(type: Literal["doi"], link: StartsWith["10.1101/"]):  # type: ignore
    def _get(url):
        data = readpage(url, format="json")
        if (
            not any(msg.get("status", None) == "ok" for msg in data["messages"])
            or not data["collection"]
        ):
            return None
        return data

    doi = link
    data = _get(f"https://api.biorxiv.org/details/biorxiv/{doi}")
    if data is None:
        data = _get(f"https://api.medrxiv.org/details/medrxiv/{doi}")
    if data is None:  # pragma: no cover
        raise Exception("Could not fetch from Bio/MedRXiv")

    entry = data["collection"][0]
    jats = entry["jatsxml"]

    links = [Link(type="doi", link=doi)]
    if entry["published"] != "NA":
        links.append(Link(type="doi", link=entry["published"]))

    return paper_from_jats(readpage(jats, format="xml"), links=links)


@register_fetch
def unpaywall(type: Literal["doi"], doi: str):
    try:
        data = readpage(
            f"https://api.unpaywall.org/v2/{doi}?email={config.mailto}",
            format="json",
        )
    except HTTPError as exc:  # pragma: no cover
        if exc.response.status_code == 404:
            return None
        else:
            raise

    date_obj = None
    date_precision = DatePrecision.year

    date_str = data["published_date"]
    date_parts = date_str.split("-")
    if len(date_parts) == 3:
        date_obj = date(int(date_parts[0]), int(date_parts[1]), int(date_parts[2]))
        date_precision = DatePrecision.day
    elif len(date_parts) == 2:
        # !! COVERAGE UNKNOWN !!
        date_obj = date(int(date_parts[0]), int(date_parts[1]), 1)
        date_precision = DatePrecision.month
    elif len(date_parts) == 1:
        # !! COVERAGE UNKNOWN !!
        date_obj = date(int(date_parts[0]), 1, 1)
        date_precision = DatePrecision.year

    releases = []
    if data.get("journal_name"):
        venue = Venue(
            name=data["journal_name"],
            type=VenueType.journal,
            series=data["journal_name"],
            aliases=[],
            links=[],
            open=data.get("journal_is_oa", False),
            peer_reviewed=True,  # Journals are typically peer reviewed
            publisher=data.get("publisher"),
            date=date_obj,
            date_precision=date_precision,
        )
        releases = [
            Release(
                venue=venue,
                status="published",
                pages=None,
            )
        ]

    authors = []
    for author_data in data.get("z_authors", []):
        author_name = author_data["raw_author_name"]
        affiliations = []
        for aff_str in (author_data.get("raw_affiliation_strings")) or []:
            affiliations.append(
                Institution(
                    name=aff_str,
                    category=InstitutionCategory.unknown,
                    aliases=[],
                )
            )

        authors.append(
            PaperAuthor(
                display_name=author_name,
                author=Author(name=author_name, aliases=[], links=[]),
                affiliations=affiliations,
            )
        )

    links = [Link(type="doi", link=doi)]

    for oa_loc in data.get("oa_locations", []):
        pdf_url = oa_loc.get("url_for_pdf")
        if pdf_url:
            links.append(Link(type="pdf", link=pdf_url))

    return Paper(
        title=data["title"],
        authors=authors,
        abstract=None,
        links=links,
        topics=[],
        releases=releases,
    )
