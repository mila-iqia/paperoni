from paperazzi.platforms.utils import Message

from paperoni.config import config
from paperoni.fulltext.pdf import PDF, CachePolicies, get_pdf
from paperoni.model.classes import (
    Author,
    Institution,
    Link,
    Paper,
    PaperAuthor,
    PaperInfo,
)
from paperoni.prompt import ParsedResponseSerializer
from paperoni.refinement.pdf.model import SYSTEM_MESSAGE, Analysis


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

    return config.refine.pdf._make_key(None, kwargs)


def prompt(pdf: PDF) -> Analysis:
    return config.refine.pdf.prompt.update(
        serializer=ParsedResponseSerializer[Analysis],
        cache_dir=pdf.directory / "prompt",
        make_key=_make_key,
        prefix=config.refine.pdf.model,
        index=0,
    )(
        client=config.refine.pdf.client,
        messages=[
            Message(type="system", prompt=SYSTEM_MESSAGE),
            Message(type="application/pdf", prompt=pdf.pdf_path),
        ],
        model=config.refine.pdf.model,
        structured_model=Analysis,
    ).parsed


def analyse_pdf(type: str, link: str) -> PaperInfo:
    key = f"{type}:{link}"
    p = get_pdf(key, cache_policy=CachePolicies.USE_BEST)

    if p is None:
        return None

    analysis = prompt(p)

    paper = Paper(
        title=None,
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
        links=[Link(type=type, link=link)],
    )
    return PaperInfo(
        paper=paper,
        key=key,
        info={"refined_by": {f"pdf-{config.refine.pdf.model}": key}},
    )
