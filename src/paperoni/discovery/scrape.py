import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import gifnoc
from bs4 import BeautifulSoup
from paperazzi.platforms.utils import Message
from paperazzi.utils import DiskStoreFunc
from serieux import deserialize, serialize

from ..config import config
from ..model.classes import DatePrecision, Link, Paper
from ..prompt import ParsedResponseSerializer
from ..prompt_utils import prompt_html, prompt_wrapper
from ..utils import url_to_id
from .base import Discoverer
from .llm_citation import model as citation_model
from .llm_selector.model import FIRST_MESSAGE, Analysis, llm_config


def _clean_dict(d: dict) -> dict:
    """Recursively clean up the dictionary removing False values unless they are
    of type int or bool"""
    if not isinstance(d, dict):
        return d

    for k, v in list(d.items()):
        if isinstance(v, dict):
            d[k] = _clean_dict(v)
        if isinstance(v, (list, tuple)):
            d[k] = [_clean_dict(item) for item in v]
        elif isinstance(v, (int, bool)):
            continue
        elif not v:
            del d[k]
    return d


def citation_prompt(
    citation: str, link: str, send_input: str, force: bool = False
) -> Paper:
    cache_dir = (
        config.data_path
        / "html"
        / hashlib.sha256(link.encode()).hexdigest()
        / citation_model.__package__.split(".")[-1]
    )

    prompt: DiskStoreFunc = config.refine.prompt.prompt.update(
        serializer=ParsedResponseSerializer[citation_model.Analysis],
        cache_dir=cache_dir / "prompt",
        prefix=config.refine.prompt.model,
        index=0,
    )
    analysis: citation_model.Analysis = prompt_wrapper(
        prompt,
        force=force,
        send_input=send_input,
        client=config.refine.prompt.client,
        messages=[
            Message(type="system", prompt=citation_model.llm_config.system_prompt),
            Message(type="user", prompt=citation_model.FIRST_MESSAGE, args=(citation,)),
        ],
        model=config.refine.prompt.model,
        structured_model=citation_model.Analysis,
    )._.parsed

    serialized_paper = _clean_dict(serialize(citation_model.Paper, analysis.paper))
    for author in serialized_paper["authors"]:
        author["author"] = {"name": author["display_name"]}
    for release in serialized_paper["releases"]:
        release["venue"] = {
            **release["venue"],
            **DatePrecision.assimilate_date(release["venue"]["date"]),
        }
        release["status"] = "unknown"

    return deserialize(Paper, serialized_paper)


@dataclass
class Scrape(Discoverer):
    # The pages to scrape
    links: list[str] = field(default_factory=lambda: links)

    # Whether to force re-running the llm prompts
    force: bool = False

    async def query(self):
        for link in self.links:
            analysis: Analysis = prompt_html(
                system_prompt=llm_config.system_prompt,
                first_message=FIRST_MESSAGE,
                structured_model=Analysis,
                link=link,
                force=self.force,
            )._.parsed

            if not analysis:
                continue

            # If paper_iteration_regex is provided, use it to further filter entries
            if analysis.paper_iteration_regex:
                paper_regex: re.Pattern = re.compile(str(analysis.paper_iteration_regex))

                def regex_iter(entry_text: str):
                    for match in paper_regex.finditer(entry_text):
                        # Use the first capture group if available, otherwise use the full match
                        if match.groups():
                            yield match.group(1)  # First capture group
                        else:
                            yield match.group(0)  # Full match

            else:

                def regex_iter(entry_text: str):
                    yield entry_text

            if analysis.link_extraction_regex:
                link_regex = re.compile(str(analysis.link_extraction_regex))

                def link_regex_iter(paper_text: str):
                    for match in link_regex.finditer(paper_text):
                        # Use the first capture group if available, otherwise use the full match
                        if match.groups():
                            yield match.group(1)  # First capture group
                        else:
                            yield match.group(0)  # Full match

            else:

                def link_regex_iter(paper_text: str):
                    del paper_text
                    yield from []

            # Fetch the cached HTML content
            soup: BeautifulSoup = await config.fetch.read(
                link,
                format="html",
                cache_into=config.data_path
                / "html"
                / hashlib.sha256(link.encode()).hexdigest()
                / "content.html",
                # The cache is updated during the llm analysis
                cache_expiry=timedelta(days=365),
            )

            for idx, entry in enumerate(soup.select(analysis.paper_selector)):
                entry_text = (
                    entry.get_text() if hasattr(entry, "get_text") else str(entry)
                )
                for citation in regex_iter(entry_text):
                    paper_links = set()
                    for url in link_regex_iter(citation + str(entry)):
                        if (_ := url_to_id(url.strip())) is not None:
                            link_type, link_url = _
                        else:
                            link_type = "url"
                            link_url = url.strip()
                        paper_links.add(Link(type=link_type, link=link_url))

                    paper = citation_prompt(
                        citation, link, send_input=f"{idx}:{link}", force=self.force
                    )

                    if paper:
                        paper.links[:] = sorted(
                            paper_links, key=lambda l: (l.type, l.link)
                        )
                        paper.key = f"scrape:{hashlib.sha256(link.encode()).hexdigest()}"
                        paper.version = datetime.now()
                        paper.info = {"discovered_by": {"scrape": link}}
                        yield paper


links: list[str] = gifnoc.define("paperoni.discovery.scrape.urls", list[str], defaults=[])
