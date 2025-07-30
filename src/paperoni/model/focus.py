import re
from bisect import bisect_left
from dataclasses import dataclass, field, replace

from ovld import ovld

from ..utils import mostly_latin
from .classes import Paper, PaperAuthor, PaperInfo


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
        return self.score(p.paper)

    @ovld
    def score(self, p: Paper):
        if not mostly_latin(p.title):
            return 0.0
        scores = [self.score(author) for author in p.authors]
        return combine(scores)

    @ovld
    def score(self, p: PaperAuthor):
        name_score = self.score_index.get(("author", p.display_name.lower()), 0.0)
        iscores = [
            self.score_index.get(("institution", name.lower()), 0.0)
            for aff in p.affiliations
            for name in re.split(r" *[,;/-] *", aff.name)
        ]
        return combine([name_score, *iscores])

    def top(self, pinfos, n, skip_zero=True):
        t = Top(n, self.score, skip_zero=skip_zero)
        t.add_all(pinfos)
        return t


class Top(list):
    def __init__(self, n, key, skip_zero=True):
        self.n = n
        self.key_func = key
        self.key = lambda x: -key(x)
        self.skip_zero = skip_zero

    def add(self, x):
        k = self.key(x)
        if self.skip_zero and k == 0:
            return
        ins = bisect_left(self, k, key=self.key)
        self.insert(ins, x)
        del self[self.n :]

    def add_all(self, elems):
        for elem in elems:
            self.add(elem)

    def resort(self):
        self.sort(key=self.key)
