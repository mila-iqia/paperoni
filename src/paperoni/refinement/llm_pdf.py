from pathlib import Path

import gifnoc
from outsight import send
from paperazzi.platforms.utils import Message

from ..config import config
from ..fulltext.pdf import PDF, CachePolicies, get_pdf
from ..model.classes import Author, Institution, Link, Paper, PaperAuthor
from ..model.merge import qual
from ..prompt import ParsedResponseSerializer
from .fetch import register_fetch
from .llm_common import Analysis, PromptConfig


def _make_key(_, kwargs: dict) -> str:
    kwargs = kwargs.copy()
    kwargs["messages"] = kwargs["messages"][:]
    for i, message in enumerate(kwargs["messages"]):
        message: Message
        if message.type == "application/pdf":
            # Use only the filename to compute the key. We do not expect the pdf
            # file to change much so most of the time we will not need to re-run
            # the prompt.
            kwargs["messages"][i] = None

    kwargs["messages"] = [m for m in kwargs["messages"] if m is not None]

    return config.refine.prompt._make_key(None, kwargs)


def prompt(pdf: PDF, force: bool = False) -> Paper:
    pdf_prompt = config.refine.prompt.prompt.update(
        serializer=ParsedResponseSerializer[Analysis],
        cache_dir=pdf.directory / "prompt",
        make_key=_make_key,
        prefix=config.refine.prompt.model,
        index=0,
    )
    prompt_kwargs = {
        "client": config.refine.prompt.client,
        "messages": [
            Message(type="system", prompt=llm_pdf_config.system_prompt),
            Message(type="application/pdf", prompt=pdf.pdf_path),
        ],
        "model": config.refine.prompt.model,
        "structured_model": Analysis,
    }

    if force:
        _, cache_file = pdf_prompt.exists(**prompt_kwargs)
        tmp_pdf_prompt = pdf_prompt.update(prefix=f".{pdf_prompt.info.store.prefix}")
        _, tmp_cache_file = tmp_pdf_prompt.exists(**prompt_kwargs)
        tmp_cache_file.unlink(missing_ok=True)
        try:
            analysis = tmp_pdf_prompt(**prompt_kwargs).parsed
        finally:
            if tmp_cache_file.exists():
                tmp_cache_file.rename(cache_file)
    else:
        analysis: Analysis = pdf_prompt(**prompt_kwargs).parsed

    return Paper(
        title=str(analysis.title),
        authors=qual(
            [
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
            100,
        ),
    )


@register_fetch(tags={"prompt", "pdf"})
def pdf(refs: list, *, force: bool = False) -> Paper:
    p = get_pdf(
        [f"{type}:{link}" for type, link in refs], cache_policy=CachePolicies.USE_BEST
    )

    if p is None:
        return None

    send(prompt=Analysis.__module__, model=config.refine.prompt.model, input=p.source.url)
    paper = prompt(p, force=force)

    if ":" in p.ref:
        type, link = p.ref.split(":", 1)
        paper.links.append(Link(type=type, link=link))

    return paper.authors and paper or None


DEFAULT_SYSTEM_MESSAGE = (Path(__file__).parent / "llm-pdf-system-prompt.md").read_text()

llm_pdf_config = gifnoc.define(
    "paperoni.llm_pdf",
    PromptConfig,
    defaults={"system_prompt_template": DEFAULT_SYSTEM_MESSAGE},
)
