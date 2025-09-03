import hashlib
from typing import Literal

from outsight import send
from paperazzi.platforms.utils import Message
from requests import HTTPError

from ...config import config
from ...model.classes import Author, Institution, Link, Paper, PaperAuthor
from ...prompt import ParsedResponseSerializer
from ..fetch import register_fetch
from .model import FIRST_MESSAGE, SYSTEM_MESSAGE, Analysis


def _make_key(_, kwargs: dict) -> str:
    kwargs = kwargs.copy()
    kwargs["messages"] = kwargs["messages"][:]
    for i, message in enumerate(kwargs["messages"]):
        message: Message
        if message.prompt == FIRST_MESSAGE:
            # Use only the link hash to compute the key. We do not expect the
            # html_content to change much so most of the time we will not need
            # to re-run the prompt.
            kwargs["messages"][i] = Message(
                type=message.type,
                prompt=message.prompt,
            )

    return config.refine.prompt._make_key(None, kwargs)


def prompt(link: str, force: bool = False) -> Paper:
    """Analyze HTML content to extract author and affiliation information."""
    try:
        html_content = config.fetch.read(link, format="txt")
    except HTTPError as exc:  # pragma: no cover
        if exc.response.status_code == 404:
            return None
        else:
            raise

    cache_dir = config.data_path / "html" / hashlib.sha256(link.encode()).hexdigest()

    html_prompt = config.refine.prompt.prompt.update(
        serializer=ParsedResponseSerializer[Analysis],
        cache_dir=cache_dir / "prompt",
        make_key=_make_key,
        prefix=config.refine.prompt.model,
        index=0,
    )
    prompt_kwargs = {
        "client": config.refine.prompt.client,
        "messages": [
            Message(type="system", prompt=SYSTEM_MESSAGE),
            Message(type="user", prompt=FIRST_MESSAGE, args=(html_content,)),
        ],
        "model": config.refine.prompt.model,
        "structured_model": Analysis,
    }

    if force:
        _, cache_file = html_prompt.exists(**prompt_kwargs)
        tmp_html_prompt = html_prompt.update(prefix=f".{html_prompt.info.store.prefix}")
        _, tmp_cache_file = tmp_html_prompt.exists(**prompt_kwargs)
        tmp_cache_file.unlink(missing_ok=True)
        try:
            analysis = tmp_html_prompt(**prompt_kwargs).parsed
        finally:
            if tmp_cache_file.exists():
                tmp_cache_file.rename(cache_file)
    else:
        analysis: Analysis = html_prompt(**prompt_kwargs).parsed

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
def html(type: Literal["doi"], link: str, force: bool = False) -> Paper:
    send(
        prompt=Analysis.__module__,
        model=config.refine.prompt.model,
        input=f"{type}:{link}",
    )

    paper = prompt(f"https://doi.org/{link}", force=force)
    paper.links.append(Link(type=type, link=link))

    return paper.authors and paper or None
