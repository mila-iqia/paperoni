from pathlib import Path
from typing import Literal

import gifnoc

from ..model.classes import Author, Institution, Link, Paper, PaperAuthor
from ..prompt import PromptConfig
from ..prompt_utils import prompt_html
from .fetch import register_fetch
from .llm_common import Analysis

FIRST_MESSAGE = """### The HTML web page of the scientific paper:

{}"""


async def prompt(link: str, send_input, force: bool = False) -> Paper:
    """Analyze HTML content to extract author and affiliation information."""
    prompt_result = await prompt_html(
        system_prompt=llm_html_config.system_prompt,
        first_message=FIRST_MESSAGE,
        structured_model=Analysis,
        link=link,
        send_input=send_input,
        force=force,
    )
    analysis: Analysis = prompt_result._.parsed

    return Paper(
        title=str(analysis.title),
        authors=[
            PaperAuthor(
                display_name=str(author_affiliations.author),
                author=Author(name=str(author_affiliations.author)),
                affiliations=[
                    Institution(name=str(affiliation))
                    for affiliation in author_affiliations.affiliations
                ],
            )
            for author_affiliations in analysis.authors_affiliations
        ],
    )


@register_fetch(tags={"prompt", "html"})
async def html(typ: Literal["doi"], link: str, *, force: bool = False) -> Paper:
    paper = await prompt(
        f"https://doi.org/{link}", send_input=f"{typ}:{link}", force=force
    )
    paper.links.append(Link(type=typ, link=link))
    return paper.authors and paper or None


DEFAULT_SYSTEM_MESSAGE = (Path(__file__).parent / "llm-html-system-prompt.md").read_text()

llm_html_config = gifnoc.define(
    "paperoni.llm_html",
    PromptConfig,
    defaults={"system_prompt_template": DEFAULT_SYSTEM_MESSAGE},
)
