from dataclasses import dataclass, field
from typing import Literal

import requests
from fake_useragent import UserAgent
from ovld import call_next, ovld

from ..config import papconf
from ..sources.acquire import readpage

ua = UserAgent()


@dataclass
class URL:
    url: str
    info: str
    headers: dict[str, str] = field(default_factory=dict)

    def readable(self):
        hd = requests.head(
            self.url, headers={"User-Agent": ua.random, **self.headers}
        )
        try:
            hd.raise_for_status()
        except Exception:
            return False
        return True


@ovld
def find_download_links(refs: list):
    for ref in refs:
        yield from call_next(ref)


@ovld
def find_download_links(ref: str):
    typ, link = ref.split(":", 1)
    yield from call_next(typ, link)


@ovld
def find_download_links(typ: Literal["arxiv"], link: str):
    """Return ArXiv PDF download link."""
    yield URL(url=f"https://export.arxiv.org/pdf/{link}.pdf", info=typ)
    yield from call_next(typ, link)


@ovld
def find_download_links(typ: Literal["openreview"], link: str):
    """Return OpenReview PDF download link."""
    yield URL(url=f"https://openreview.net/pdf?id={link}", info=typ)
    yield from call_next(typ, link)


@ovld
def find_download_links(typ: Literal["pdf", "pdf.official"], link: str):
    """Direct link to a PDF."""
    yield URL(url=link, info=typ)
    yield from call_next(typ, link)


@ovld(priority=100)
def find_download_links(typ: Literal["doi"], link: str):
    """Find links from ScienceDirect DOI entry (needs token)."""
    key = papconf.tokens.elsevier
    if key:
        yield URL(
            url=f"https://api.elsevier.com/content/article/doi/{link}?apiKey={key}&httpAccept=application%2Fpdf",
            info="doi.sciencedirect",
        )
    yield from call_next(typ, link)


@ovld(priority=90)
def find_download_links(typ: Literal["doi"], link: str):
    """Find links from CrossRef DOI entry."""
    try:
        data = readpage(
            f"https://api.crossref.org/v1/works/{link}",
            format="json",
        )
    except requests.HTTPError:
        return None
    if data is None or data["status"] != "ok":
        return None
    data = data["message"]
    if "link" in data:
        for lnk in data["link"]:
            if lnk["content-type"] == "application/pdf":
                yield URL(url=lnk["URL"], info="doi.crossref")
    yield from call_next(typ, link)


@ovld(priority=80)
def find_download_links(typ: Literal["doi"], link: str):
    """Find links from OpenAlex, searching by DOI."""
    mailto = f"mailto={papconf.mailto}" if papconf.mailto else ""
    url = f"https://api.openalex.org/works/doi:{link}?{mailto}&select=open_access,title"
    try:
        results = readpage(url, format="json")
    except requests.HTTPError:
        return
    oa = results["open_access"]
    if oa["is_oa"]:
        yield URL(url=oa["oa_url"], info="doi.openalex")
    yield from call_next(typ, link)


@ovld(priority=1)
def find_download_links(typ: Literal["doi"], link: str):
    """Find links from whatever the DOI handle redirects to."""
    info = readpage(f"https://doi.org/api/handles/{link}", format="json")
    target = [v for v in info["values"] if v["type"] == "URL"][0]["data"][
        "value"
    ]
    try:
        soup = readpage(
            target, format="html", headers={"User-Agent": ua.random}
        )
    except requests.HTTPError:
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
    yield from call_next(typ, link)


@ovld(priority=-10)
def find_download_links(typ: str, link: str):
    yield from []
