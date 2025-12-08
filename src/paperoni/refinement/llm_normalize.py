import logging
import re
from datetime import datetime

from paperazzi.platforms.utils import Message
from paperazzi.utils import DiskStoreFunc

from ..config import config
from ..model import DatePrecision
from ..model.classes import Institution, InstitutionCategory, Paper, Venue
from ..prompt import ParsedResponseSerializer
from ..prompt_utils import prompt_wrapper
from ..utils import normalize_institution, normalize_name, normalize_venue
from .llm_norm_author import model as norm_author_model
from .llm_norm_venues import model as norm_venue_model
from .llm_process_affiliation import model as process_affiliation_model


def process_affiliations_prompt(
    affiliation: Institution, force: bool = False
) -> list[Institution]:
    cache_dir = (
        config.data_path
        / process_affiliation_model.__package__.split(".")[-1]
        / re.sub(r"[^a-zA-Z0-9]+", "_", normalize_institution(affiliation.name))
    )

    prompt: DiskStoreFunc = config.refine.prompt.prompt.update(
        serializer=ParsedResponseSerializer[process_affiliation_model.Analysis],
        cache_dir=cache_dir / "prompt",
        prefix=config.refine.prompt.model,
        index=0,
    )
    analysis: process_affiliation_model.Analysis = prompt_wrapper(
        prompt,
        force=force,
        send_input=affiliation.name,
        client=config.refine.prompt.client,
        messages=[
            Message(
                type="system",
                prompt=process_affiliation_model.llm_config.system_prompt,
            ),
            Message(
                type="user",
                prompt=process_affiliation_model.FIRST_MESSAGE,
                args=(affiliation.name,),
            ),
        ],
        model=config.refine.prompt.model,
        structured_model=process_affiliation_model.Analysis,
    )._.parsed

    return [
        Institution(
            name=str(aff.name),
            category=(
                affiliation.category
                if affiliation.category != InstitutionCategory.unknown
                else InstitutionCategory(aff.category)
            ),
            country=str(aff.country) or None,
            aliases=[
                aff_name
                for aff_name in [affiliation.name, *affiliation.aliases]
                if aff_name != aff.name
            ],
        )
        for aff in analysis.affiliations
    ]


def norm_author_display_name_prompt(display_name: str, force: bool = False) -> str:
    cache_dir = (
        config.data_path
        / norm_author_model.__package__.split(".")[-1]
        / re.sub(r"[^a-zA-Z0-9]+", "_", normalize_name(display_name))
    )

    prompt: DiskStoreFunc = config.refine.prompt.prompt.update(
        serializer=ParsedResponseSerializer[norm_author_model.Analysis],
        cache_dir=cache_dir / "prompt",
        prefix=config.refine.prompt.model,
        index=0,
    )
    analysis: norm_author_model.Analysis = prompt_wrapper(
        prompt,
        force=force,
        send_input=display_name,
        client=config.refine.prompt.client,
        messages=[
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
        model=config.refine.prompt.model,
        structured_model=norm_author_model.Analysis,
    )._.parsed

    return str(analysis.normalized_author)


def norm_venue_prompt(venue: Venue, force: bool = False) -> Venue:
    cache_dir = (
        config.data_path
        / norm_venue_model.__package__.split(".")[-1]
        / re.sub(r"[^a-zA-Z0-9]+", "_", normalize_venue(venue.name))
    )

    prompt: DiskStoreFunc = config.refine.prompt.prompt.update(
        serializer=ParsedResponseSerializer[norm_venue_model.Analysis],
        cache_dir=cache_dir / "prompt",
        prefix=config.refine.prompt.model,
        index=0,
    )
    analysis: norm_venue_model.Analysis = prompt_wrapper(
        prompt,
        force=force,
        send_input=venue.name,
        client=config.refine.prompt.client,
        messages=[
            Message(
                type="system",
                prompt=norm_venue_model.llm_config.system_prompt,
            ),
            Message(
                type="user",
                prompt=norm_venue_model.FIRST_MESSAGE,
                args=(venue.name,),
            ),
        ],
        model=config.refine.prompt.model,
        structured_model=norm_venue_model.Analysis,
    )._.parsed

    year = {}
    if analysis.year:
        try:
            year = {
                "date": datetime.strptime(str(analysis.year), "%Y").date(),
                "date_precision": DatePrecision.year,
            }
        except ValueError:
            logging.warning(
                f"Failed to parse year {analysis.year} from venue llm analysis for {venue.name}"
            )

    return Venue(
        **{
            **vars(venue),
            "name": str(analysis.name),
            "short_name": str(analysis.short_name) or venue.short_name,
            "volume": str(analysis.numeric_marker) or venue.volume,
            **year,
        }
    )


def normalize_paper(
    paper: Paper, *, author=True, venue=True, institution=True, force: bool = False
) -> Paper:
    norm_authors = author
    norm_venues = venue
    norm_institutions = institution

    for author in paper.authors:
        if norm_institutions:
            for i, affiliation in enumerate(author.affiliations[:]):
                affiliations = process_affiliations_prompt(affiliation, force)
                if not affiliations:
                    logging.warning(
                        f"LLM returned no affiliations from {affiliation.name}"
                    )
                    continue
                if affiliations[0] != author.affiliations[i]:
                    author.affiliations[i] = affiliations[0]
                author.affiliations.extend(affiliations[1:])

        if norm_authors:
            display_name = norm_author_display_name_prompt(author.display_name, force)
            if display_name != author.display_name:
                author.author.aliases = [author.author.name, *author.author.aliases]
                author.author.name = author.display_name
                author.display_name = display_name

    if norm_venues:
        for release in paper.releases:
            venue = norm_venue_prompt(release.venue, force)
            if venue != release.venue:
                if (
                    venue.name != release.venue.name
                    and release.venue.name not in venue.aliases
                ):
                    venue.aliases = [release.venue.name, *venue.aliases]
                release.venue = venue

    return paper
