import re

from outsight import send
from paperazzi.platforms.utils import Message
from paperazzi.utils import DiskStoreFunc

from ..config import config
from ..model.classes import Institution, Paper
from ..prompt import ParsedResponseSerializer
from ..utils import normalize_institution, normalize_name
from .llm_norm_affiliation import model as norm_affiliation_model
from .llm_norm_author import model as norm_author_model
from .llm_utils import force_prompt


def norm_affiliations_prompt(
    affiliation: Institution, force: bool = False
) -> list[Institution]:
    send(
        prompt=norm_affiliation_model.Analysis.__module__,
        model=config.refine.prompt.model,
        input=affiliation.name,
    )

    cache_dir = (
        config.data_path
        / norm_affiliation_model.__package__.split(".")[-1]
        / re.sub(r"[^a-zA-Z0-9]+", "_", normalize_institution(affiliation.name))
    )

    prompt: DiskStoreFunc = config.refine.prompt.prompt.update(
        serializer=ParsedResponseSerializer[norm_affiliation_model.Analysis],
        cache_dir=cache_dir / "prompt",
        make_key=config.refine.prompt._make_key,
        prefix=config.refine.prompt.model,
        index=0,
    )
    prompt_kwargs = {
        "client": config.refine.prompt.client,
        "messages": [
            Message(
                type="system",
                prompt=norm_affiliation_model.llm_config.system_prompt,
            ),
            Message(
                type="user",
                prompt=norm_affiliation_model.FIRST_MESSAGE,
                args=(affiliation.name,),
            ),
        ],
        "model": config.refine.prompt.model,
        "structured_model": norm_affiliation_model.Analysis,
    }

    if force:
        analysis: norm_affiliation_model.Analysis = force_prompt(
            prompt, **prompt_kwargs
        ).parsed
    else:
        analysis: norm_affiliation_model.Analysis = prompt(**prompt_kwargs).parsed

    return [
        Institution(
            name=str(aff),
            category=affiliation.category,
            aliases=[affiliation.name, *affiliation.aliases],
        )
        for aff in analysis.normalized_affiliations
    ]


def norm_author_display_name_prompt(display_name: str, force: bool = False) -> str:
    send(
        prompt=norm_author_model.Analysis.__module__,
        model=config.refine.prompt.model,
        input=display_name,
    )

    cache_dir = (
        config.data_path
        / norm_author_model.__package__.split(".")[-1]
        / re.sub(r"[^a-zA-Z0-9]+", "_", normalize_name(display_name))
    )

    prompt: DiskStoreFunc = config.refine.prompt.prompt.update(
        serializer=ParsedResponseSerializer[norm_author_model.Analysis],
        cache_dir=cache_dir / "prompt",
        make_key=config.refine.prompt._make_key,
        prefix=config.refine.prompt.model,
        index=0,
    )
    prompt_kwargs = {
        "client": config.refine.prompt.client,
        "messages": [
            Message(
                type="system",
                prompt=norm_author_model.llm_config.system_prompt,
            ),
            Message(
                type="user",
                prompt=norm_author_model.FIRST_MESSAGE,
                args=(display_name,),
            ),
        ],
        "model": config.refine.prompt.model,
        "structured_model": norm_author_model.Analysis,
    }

    if force:
        analysis: norm_author_model.Analysis = force_prompt(
            prompt, **prompt_kwargs
        ).parsed
    else:
        analysis: norm_author_model.Analysis = prompt(**prompt_kwargs).parsed

    return str(analysis.normalized_author)


def normalize_paper(paper: Paper, *, force: bool = False) -> Paper:
    for author in paper.authors:
        for i, affiliation in enumerate(author.affiliations[:]):
            affiliations = norm_affiliations_prompt(affiliation, force)
            if affiliations[0].name != author.affiliations[i].name:
                author.affiliations[i] = affiliations[0]
            author.affiliations.extend(affiliations[1:])

        display_name = norm_author_display_name_prompt(author.display_name, force)
        if display_name != author.display_name:
            author.author.aliases = [author.author.name, *author.author.aliases]
            author.author.name = author.display_name
            author.display_name = display_name

    return paper
