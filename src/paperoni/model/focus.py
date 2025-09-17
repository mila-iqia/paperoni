from dataclasses import dataclass, field, replace
from heapq import heapify, heappush, heappushpop
from typing import Counter, Iterable

from outsight import send
from ovld import ovld

from ..utils import (
    mostly_latin,
    normalize_institution,
    normalize_name,
    split_institution,
)
from .classes import Paper, PaperAuthor, PaperInfo
from .merge import PaperWorkingSet


@dataclass
class Focus:
    type: str
    name: str
    score: float
    drive_discovery: bool = False

    @classmethod
    def encode(cls, f):
        drive_prefix = "!" if f.drive_discovery else ""
        return f"{drive_prefix}{f.type}::{f.name}::{f.score}"

    @classmethod
    def decode(cls, s: str):
        drive_discovery = s.startswith("!")
        if drive_discovery:
            s = s[1:]
        type_name, name, score_str = [x.strip() for x in s.split("::")]
        score = float(score_str)
        return cls(
            type=type_name, name=name, score=score, drive_discovery=drive_discovery
        )

    @classmethod
    def serieux_model(cls, call_next):
        return replace(
            call_next(cls),
            from_string=cls.decode,
            to_string=cls.encode,
        )


def combine(scores):
    return sum(scores)


@dataclass
class Focuses:
    focuses: list[Focus] = field(default_factory=list)

    def __post_init__(self):
        self.score_index = {(f.type, f.name.lower()): f.score for f in self.focuses}

    @classmethod
    def serieux_deserialize(cls, obj, ctx, call_next):
        return cls(call_next(list[Focus], obj, ctx))

    @classmethod
    def serieux_serialize(cls, obj, ctx, call_next):
        return call_next(list[Focus], obj.focuses, ctx)

    @ovld
    def score(self, p: PaperInfo):
        score = self.score(p.paper)
        send(score=score)
        return score

    @ovld
    def score(self, p: PaperWorkingSet):
        return self.score(p.current)

    @ovld
    def score(self, p: Paper):
        if not mostly_latin(p.title):
            return 0.0
        scores = [self.score(author) for author in p.authors]
        return combine(scores)

    @ovld
    def score(self, p: PaperAuthor):
        name_score = self.score_index.get(("author", normalize_name(p.display_name)), 0.0)
        iscores = [
            self.score_index.get(("institution", normalize_institution(name)), 0.0)
            for aff in p.affiliations
            for name in split_institution(aff.name)
        ]
        return combine([name_score, *iscores])

    def top(self, pinfos, n, drop_zero=True):
        t = Top(n, drop_zero=drop_zero)
        for p in pinfos:
            scored = Scored(self.score(p), p)
            t.add(scored)
        return t

    def update(self, papers: Iterable[Paper], autofocus: "AutoFocus") -> "Focuses":
        focused_institutions_cnts = {
            normalize_institution(f.name): Counter()
            for f in self.focuses
            if f.type == "institution"
        }
        focused_authors = {f.name for f in self.focuses if f.type == "author"}

        for paper in papers:
            for author in paper.authors:
                for aff_name in sum(
                    map(lambda x: split_institution(x.name), author.affiliations), []
                ):
                    aff_name = normalize_institution(aff_name)
                    if aff_name in focused_institutions_cnts:
                        focused_institutions_cnts[aff_name].update(
                            set([author.display_name, *author.author.aliases])
                        )

        for counter in focused_institutions_cnts.values():
            for author_name, count in counter.most_common():
                if (
                    count >= autofocus.author.threshold
                    and author_name not in focused_authors
                ):
                    self.focuses.append(
                        Focus(
                            type="author", name=author_name, score=autofocus.author.score
                        )
                    )
                    focused_authors.add(author_name)

        # sort focuses by institution first, then author
        self.focuses = sorted(
            (f for f in self.focuses if f.type == "institution"),
            key=lambda x: x.score,
            reverse=True,
        ) + sorted(
            (f for f in self.focuses if f.type == "author"),
            key=lambda x: x.score,
            reverse=True,
        )


class AutoFocus(dict[str, "AutoFocus.Type"]):
    @dataclass
    class Type:
        score: int
        threshold: int

    def __getitem__(self, key: str, /) -> "AutoFocus.Type":
        return super().__getitem__(key)

    def __getattr__(self, attr: str) -> "AutoFocus.Type":
        return self[attr]


@dataclass(order=True)
class Scored[T]:
    score: float
    value: T = field(compare=False)

    def __bool__(self):
        return self.score != 0


@dataclass
class Top[T]:
    n: int
    entries: list[T] = field(default_factory=list)
    drop_zero: bool = True

    def __post_init__(self):
        xs, self.entries = self.entries, []
        self.add_all(xs)

    def add(self, x):
        if self.drop_zero and not x:
            return
        if len(self.entries) >= self.n:
            heappushpop(self.entries, x)
        else:
            heappush(self.entries, x)

    def add_all(self, elems):
        for elem in elems:
            self.add(elem)

    def discard_all(self, elems):
        ids = {id(e) for e in elems}
        self.entries = [e for e in self.entries if id(e) not in ids]
        heapify(self.entries)

    def resort(self):
        self.entries = [e for e in self.entries if e]
        heapify(self.entries)

    def __len__(self):
        return len(self.entries)

    def __iter__(self):
        yield from sorted(self.entries, reverse=True)
