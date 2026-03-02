import textwrap
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Callable

from ovld import call_next, ovld, recurse

from .model import (
    Author,
    Institution,
    Link,
    Paper,
    PaperAuthor,
    Release,
    Topic,
    Venue,
)
from .utils import release_status_order


@dataclass
class OperationResult:
    changed: bool
    original: Paper
    new: Paper = None


@dataclass
class FlagSetter:
    operation: Callable[[Paper], bool]
    true_flag: str
    false_flag: str = None

    def locked(self, p: Paper):
        return (self.true_flag and f"lock-{self.true_flag}" in p.flags) or (
            self.false_flag and f"lock-{self.false_flag}" in p.flags
        )

    def __call__(self, p: Paper):
        new_flags = set(p.flags)
        if not self.locked(p):
            if result := self.operation(p):
                if self.true_flag:
                    new_flags.add(self.true_flag)
                new_flags.discard(self.false_flag)
            elif result is False:
                if self.false_flag:
                    new_flags.add(self.false_flag)
                new_flags.discard(self.true_flag)
            else:
                new_flags.discard(self.true_flag)
                new_flags.discard(self.false_flag)
        changed = p.flags != new_flags
        return OperationResult(
            changed=changed,
            original=p,
            new=replace(p, flags=new_flags) if changed else p,
        )


def flag_setter(true_flag: str, false_flag: str = None):
    def deco(fn):
        return FlagSetter(fn, true_flag=true_flag, false_flag=false_flag)

    return deco


def operation(fn):
    def deco(p: Paper):
        new = fn(p)
        return OperationResult(
            changed=p != new,
            original=p,
            new=new,
        )

    return deco


@ovld
def paper_map(x: str | int | float | bool | type(None) | date | datetime):
    return x


@ovld(priority=0)
def paper_map(x: object):
    """Pass-through for enums and other unhandled types."""
    return x


@ovld
def paper_map(x: list):
    return [recurse(item) for item in x]


@ovld
def paper_map(x: dict):
    return {k: recurse(v) for k, v in x.items()}


@ovld
def paper_map(x: set):
    return {recurse(item) for item in x}


@ovld
def paper_map(x: Link):
    return Link(type=recurse(x.type), link=recurse(x.link))


@ovld
def paper_map(x: Topic):
    return Topic(name=recurse(x.name))


@ovld
def paper_map(x: Author):
    return Author(
        name=recurse(x.name),
        aliases=recurse(x.aliases),
        links=recurse(x.links),
    )


@ovld
def paper_map(x: Institution):
    return Institution(
        name=recurse(x.name),
        category=x.category,
        country=recurse(x.country),
        aliases=recurse(x.aliases),
    )


@ovld
def paper_map(x: Venue):
    return Venue(
        type=x.type,
        name=recurse(x.name),
        series=recurse(x.series),
        date=x.date,
        date_precision=x.date_precision,
        volume=recurse(x.volume),
        publisher=recurse(x.publisher),
        short_name=recurse(x.short_name),
        aliases=recurse(x.aliases),
        links=recurse(x.links),
        open=x.open,
        peer_reviewed=x.peer_reviewed,
    )


@ovld
def paper_map(x: Release):
    return Release(
        venue=recurse(x.venue),
        status=recurse(x.status),
        pages=recurse(x.pages),
        peer_review_status=x.peer_review_status,
    )


@ovld
def paper_map(x: PaperAuthor):
    return PaperAuthor(
        author=recurse(x.author),
        display_name=recurse(x.display_name),
        affiliations=recurse(x.affiliations),
    )


@ovld
def paper_map(p: Paper):
    return Paper(
        title=recurse(p.title),
        abstract=recurse(p.abstract),
        authors=recurse(p.authors),
        releases=recurse(p.releases),
        topics=recurse(p.topics),
        links=recurse(p.links),
        flags=recurse(p.flags),
        key=recurse(p.key),
        info=recurse(p.info),
        score=p.score,
        id=p.id,
        version=p.version,
    )


_builtins = {
    "paper_map": paper_map,
    "Paper": Paper,
    "PaperAuthor": PaperAuthor,
    "Author": Author,
    "Institution": Institution,
    "Link": Link,
    "Topic": Topic,
    "Venue": Venue,
    "Release": Release,
    "OperationResult": OperationResult,
    "replace": replace,
    "ovld": ovld,
    "recurse": recurse,
    "call_next": call_next,
}


def from_code(code):
    prelude = None
    sep = "\n#####\n"
    if sep in code:
        prelude, code = code.split("#####")

    glb = dict(_builtins)
    if prelude:
        exec(prelude, glb, glb)

    indented_code = textwrap.indent(code, "    ")
    opcode = f"def __operate(paper):\n{indented_code}"
    exec(opcode, glb, glb)
    func = glb["__operate"]

    def deco(p: Paper):
        result = func(p)
        if result is None:
            raise Exception(
                "The code block should not return None; return False to signify no change"
            )
        elif isinstance(result, bool):
            return OperationResult(changed=result, original=p, new=None)
        elif isinstance(result, Paper):
            return OperationResult(
                changed=p != result,
                original=p,
                new=result,
            )
        else:
            return result

    return deco


######################
# Defined operations #
######################


@flag_setter("peer-reviewed")
def peer_reviewed(p: Paper):
    return any(r.peer_review_status == "peer-reviewed" for r in p.releases)


@operation
def sort_releases(p: Paper):
    releases = [(release, release_status_order(release)) for release in p.releases]
    releases.sort(key=lambda entry: -entry[1])
    return replace(p, releases=[r for r, _ in releases])


@operation
def rescore(p: Paper):
    from .config import config

    new_score = config.focuses.score(p)
    return replace(p, score=new_score)


@flag_setter("valid")
def auto_validate(p: Paper):
    from .config import config

    return p.score >= config.autovalidation_threshold
