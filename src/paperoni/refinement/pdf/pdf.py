from paperazzi.platforms.utils import Message

from paperoni.config import config
from paperoni.fulltext.pdf import CachePolicies, get_pdf
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


def analyse_pdf(type: str, link: str) -> PaperInfo:
    key = f"{type}:{link}"
    p = get_pdf(key, cache_policy=CachePolicies.USE_BEST)

    if p is None:
        return None

    analysis: Analysis = config.refine.pdf.prompt.update(
        serializer=ParsedResponseSerializer[Analysis],
        cache_dir=p.directory / "prompt",
        prefix=config.refine.pdf.model,
        index=0,
    )(
        client=config.refine.pdf.client,
        messages=[
            Message(type="system", prompt=SYSTEM_MESSAGE),
            Message(type="application/pdf", prompt=p.pdf_path),
        ],
        model=config.refine.pdf.model,
        structured_model=Analysis,
    ).parsed

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
