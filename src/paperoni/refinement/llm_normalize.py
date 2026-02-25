import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from paperazzi.platforms.utils import Message
from paperazzi.utils import DiskStoreFunc

from ..config import config
from ..model import DatePrecision, PaperAuthor, Release, VenueType
from ..model.classes import Institution, InstitutionCategory, Paper, Venue
from ..prompt import ParsedResponseSerializer
from ..prompt_utils import prompt_wrapper
from ..utils import normalize_institution, normalize_name, normalize_venue
from .llm_norm_author import model as norm_author_model
from .llm_norm_venue import model as norm_venue_model
from .llm_process_affiliation import model as process_affiliation_model


def process_affiliations_prompt(
    affiliation: Institution,
    force: bool = False,
    *,
    client: Any = None,
    prompt: DiskStoreFunc = None,
    model: str = None,
    data_path: Path = None,
) -> list[Institution]:
    cache_dir = (
        (data_path or config.data_path)
        / process_affiliation_model.__package__.split(".")[-1]
        / re.sub(r"[^a-zA-Z0-9]+", "_", normalize_institution(affiliation.name))
    )

    prompt: DiskStoreFunc = (prompt or config.refine.prompt.prompt).update(
        serializer=ParsedResponseSerializer[process_affiliation_model.Analysis],
        cache_dir=cache_dir / "prompt",
        prefix=(model or config.refine.prompt.model),
        index=0,
    )
    analysis: process_affiliation_model.Analysis = prompt_wrapper(
        prompt,
        force=force,
        send_input=affiliation.name,
        client=(client or config.refine.prompt.client),
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
        model=(model or config.refine.prompt.model),
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


def norm_author_display_name_prompt(
    display_name: str,
    force: bool = False,
    *,
    client: Any = None,
    prompt: DiskStoreFunc = None,
    model: str = None,
    data_path: Path = None,
) -> str:
    cache_dir = (
        (data_path or config.data_path)
        / norm_author_model.__package__.split(".")[-1]
        / re.sub(r"[^a-zA-Z0-9]+", "_", normalize_name(display_name))
    )

    prompt: DiskStoreFunc = (prompt or config.refine.prompt.prompt).update(
        serializer=ParsedResponseSerializer[norm_author_model.Analysis],
        cache_dir=cache_dir / "prompt",
        prefix=(model or config.refine.prompt.model),
        index=0,
    )
    analysis: norm_author_model.Analysis = prompt_wrapper(
        prompt,
        force=force,
        send_input=display_name,
        client=(client or config.refine.prompt.client),
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
        model=(model or config.refine.prompt.model),
        structured_model=norm_author_model.Analysis,
    )._.parsed

    return str(analysis.normalized_author)


def norm_venue_prompt(
    venue: Venue,
    force: bool = False,
    *,
    client: Any = None,
    prompt: DiskStoreFunc = None,
    model: str = None,
    data_path: Path = None,
) -> Venue:
    cache_dir = (
        (data_path or config.data_path)
        / norm_venue_model.__package__.split(".")[-1]
        / re.sub(r"[^a-zA-Z0-9]+", "_", normalize_venue(venue.name))
    )

    prompt: DiskStoreFunc = (prompt or config.refine.prompt.prompt).update(
        serializer=ParsedResponseSerializer[norm_venue_model.Analysis],
        cache_dir=cache_dir / "prompt",
        prefix=(model or config.refine.prompt.model),
        index=0,
    )
    analysis: norm_venue_model.Analysis = prompt_wrapper(
        prompt,
        force=force,
        send_input=venue.name,
        client=(client or config.refine.prompt.client),
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
        model=(model or config.refine.prompt.model),
        structured_model=norm_venue_model.Analysis,
    )._.parsed

    year = {}
    if analysis.year and venue.date_precision <= DatePrecision.year:
        try:
            year = {
                "date": datetime.strptime(str(analysis.year).strip(), "%Y").date(),
                "date_precision": DatePrecision.year,
            }
        except ValueError:
            logging.warning(
                f"Failed to parse year {analysis.year} from venue llm analysis for {venue.name}"
            )

    venue_name = str(analysis.name).strip() or venue.name
    venue_short_name = str(analysis.short_name).strip() or venue.short_name
    workshop_name = str(analysis.workshop_name).strip()
    venue_type = venue.type
    if workshop_name:
        venue_name = f"{workshop_name} @ {venue_name}"
        venue_short_name = f"{workshop_name}@{venue_short_name}"
        venue_type = VenueType.workshop

    return Venue(
        **{
            **vars(venue),
            "type": venue_type,
            "name": venue_name,
            "short_name": venue_short_name,
            "volume": str(analysis.numeric_marker).strip() or venue.volume,
            **year,
        }
    )


def normalize_paper(
    paper: Paper, *, author=True, venue=True, institution=True, force: bool = False
) -> Paper:
    # Explicitly pass `client`, `prompt`, `model`, and `data_path` as `config`
    # will get reinitialized in each thread, losing any overlays applied.
    # `config` is also currently not serializable, including with
    # `serieux.serialize`, so we can't use it directly.
    client = config.refine.prompt.client
    prompt = config.refine.prompt.prompt
    model = config.refine.prompt.model
    data_path = config.data_path

    norm_authors = author
    norm_venues = venue
    norm_institutions = institution

    futures = []

    with ThreadPoolExecutor() as executor:
        for author in paper.authors:
            if norm_institutions:
                for i, affiliation in enumerate(author.affiliations[:]):

                    def task(author: PaperAuthor, affiliation: Institution, i: int):
                        affiliations = process_affiliations_prompt(
                            affiliation,
                            force,
                            client=client,
                            prompt=prompt,
                            model=model,
                            data_path=data_path,
                        )
                        if not affiliations:
                            logging.warning(
                                f"LLM returned no affiliations from {affiliation.name}"
                            )
                            return
                        if affiliations[0] != author.affiliations[i]:
                            author.affiliations[i] = affiliations[0]
                        author.affiliations.extend(affiliations[1:])

                    futures.append(
                        executor.submit(task, author=author, affiliation=affiliation, i=i)
                    )

            if norm_authors:

                def task(author: PaperAuthor):
                    display_name = norm_author_display_name_prompt(
                        author.display_name,
                        force,
                        client=client,
                        prompt=prompt,
                        model=model,
                        data_path=data_path,
                    )
                    if display_name != author.display_name:
                        author.author.aliases = [
                            author.author.name,
                            *author.author.aliases,
                        ]
                        author.author.name = author.display_name
                        author.display_name = display_name

                futures.append(executor.submit(task, author=author))

        if norm_venues:
            for release in paper.releases:

                def task(release: Release):
                    venue = norm_venue_prompt(
                        release.venue,
                        force,
                        client=client,
                        prompt=prompt,
                        model=model,
                        data_path=data_path,
                    )
                    if venue != release.venue:
                        if (
                            venue.name != release.venue.name
                            and release.venue.name not in venue.aliases
                        ):
                            venue.aliases = [release.venue.name, *venue.aliases]
                        release.venue = venue

                futures.append(executor.submit(task, release=release))

    for fut in as_completed(futures):
        fut.result()

    return paper
