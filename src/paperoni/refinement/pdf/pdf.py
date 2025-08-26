from paperazzi.platforms.utils import Message

from ...config import config
from ...fulltext.pdf import PDF, CachePolicies, get_pdf
from ...model.classes import Author, Institution, Link, Paper, PaperAuthor, PaperInfo
from ...prompt import ParsedResponseSerializer
from .model import SYSTEM_MESSAGE, Analysis


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


def prompt(pdf: PDF, force: bool = False) -> Analysis:
    pdf_prompt = config.refine.pdf.prompt.update(
        serializer=ParsedResponseSerializer[Analysis],
        cache_dir=pdf.directory / "prompt",
        make_key=_make_key,
        prefix=config.refine.pdf.model,
        index=0,
    )
    prompt_kwargs = {
        "client": config.refine.pdf.client,
        "messages": [
            Message(type="system", prompt=SYSTEM_MESSAGE),
            Message(type="application/pdf", prompt=pdf.pdf_path),
        ],
        "model": config.refine.pdf.model,
        "structured_model": Analysis,
    }

    if force:
        _, cache_file = pdf_prompt.exists(**prompt_kwargs)
        tmp_pdf_prompt = pdf_prompt.update(prefix=f".{pdf_prompt.info.store.prefix}")
        _, tmp_cache_file = tmp_pdf_prompt.exists(**prompt_kwargs)
        tmp_cache_file.unlink(missing_ok=True)
        try:
            return tmp_pdf_prompt(**prompt_kwargs).parsed
        finally:
            if tmp_cache_file.exists():
                tmp_cache_file.rename(cache_file)
    else:
        return pdf_prompt(**prompt_kwargs).parsed


def analyse_pdf(type: str, link: str, force: bool = False) -> PaperInfo:
    key = f"{type}:{link}"
    p = get_pdf(key, cache_policy=CachePolicies.USE_BEST)

    if p is None:
        return None

    analysis = prompt(p, force=force)

    paper = Paper(
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
        links=[Link(type=type, link=link)],
    )
    return PaperInfo(
        paper=paper,
        key=key,
        info={"refined_by": {f"pdf-{config.refine.pdf.model}": key}},
    )
