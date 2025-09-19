from dataclasses import dataclass, field
from typing import Literal

from ovld import call_next, ovld
from requests import HTTPError

from ..config import config


@dataclass
class URL:
    url: str
    info: str
    headers: dict[str, str] = field(default_factory=dict)

    def readable(self):
        hd = config.fetch.head(self.url, headers=self.headers)
        try:
            hd.raise_for_status()
        except Exception:
            return False
        return True


@ovld
def find_download_links(typ: Literal["arxiv"], link: str):
    """Return ArXiv PDF download link."""
    yield URL(url=f"https://export.arxiv.org/pdf/{link}.pdf", info=typ)


@ovld
def find_download_links(typ: Literal["openreview"], link: str):
    """Return OpenReview PDF download link."""
    yield URL(url=f"https://openreview.net/pdf?id={link}", info=typ)


@ovld
def find_download_links(typ: Literal["pdf", "pdf.official"], link: str):
    """Direct link to a PDF."""
    yield URL(url=link, info=typ)


@ovld(priority=100)
def find_download_links(typ: Literal["doi"], link: str):
    """Find links from Wiley DOI entry (needs token)."""
    if key := config.api_keys.wiley:
        url = URL(
            url=f"https://api.wiley.com/onlinelibrary/tdm/v1/articles/{link}",
            headers={"Wiley-TDM-Client-Token": key},
            info="doi.wiley",
        )
        if url.readable():
            yield url


@ovld(priority=100)
def find_download_links(typ: Literal["doi"], link: str):
    """Find links from ScienceDirect DOI entry (needs token)."""
    if key := config.api_keys.elsevier:
        url = URL(
            url=f"https://api.elsevier.com/content/article/doi/{link}?apiKey={key}&httpAccept=application%2Fpdf",
            info="doi.sciencedirect",
        )
        if url.readable():
            yield url


@ovld(priority=90)
def find_download_links(typ: Literal["doi"], link: str):
    """Find links from CrossRef DOI entry."""
    try:
        data = config.fetch.read(
            f"https://api.crossref.org/v1/works/{link}",
            format="json",
        )
    except HTTPError:
        return None
    if data is None or data["status"] != "ok":
        return None
    data = data["message"]
    if "link" in data:
        for lnk in data["link"]:
            if lnk["content-type"] == "application/pdf":
                yield URL(url=lnk["URL"], info="doi.crossref")


@ovld(priority=80)
def find_download_links(typ: Literal["doi"], link: str):
    """Find links from OpenAlex, searching by DOI."""
    mailto = f"mailto={config.mailto}" if config.mailto else ""
    url = f"https://api.openalex.org/works/doi:{link}?{mailto}&select=open_access,title"
    try:
        results = config.fetch.read(url, format="json")
    except HTTPError:
        return
    oa = results["open_access"]
    if oa["is_oa"]:
        yield URL(url=oa["oa_url"], info="doi.openalex")


@ovld(priority=1)
def find_download_links(typ: Literal["doi"], link: str):
    """Find links from whatever the DOI handle redirects to."""
    info = config.fetch.read(f"https://doi.org/api/handles/{link}", format="json")
    target = [v for v in info["values"] if v["type"] == "URL"][0]["data"]["value"]
    try:
        soup = config.fetch.read(target, format="html")
    except HTTPError:
        return None
    possible_selectors = {
        'meta[name="citation_pdf_url"]': "content",
        'a[title="View PDF"]': "href",
        'a[title="Download PDF"]': "href",
    }
    for sel, attr in possible_selectors.items():
        tag = soup.select_one(sel)
        if tag and (result := tag.attrs.get(attr, None)):
            yield URL(url=result, info="doi.handler")


@ovld
def locate_all(refs: list):
    for ref in refs:
        yield from call_next(ref)


@ovld
def locate_all(ref: str):
    typ, link = ref.split(":", 1)
    yield from call_next(typ, link)


@ovld
def locate_all(typ: str, link: str):
    seen = set()
    for f in find_download_links.resolve_all(typ, link):
        for url in f():
            if url.url not in seen:
                seen.add(url.url)
                yield url
