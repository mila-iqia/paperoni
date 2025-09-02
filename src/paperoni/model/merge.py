from dataclasses import dataclass, field
from difflib import SequenceMatcher
from numbers import Number

from ovld import Dataclass, call_next, ovld, recurse
from serieux.features.comment import CommentProxy

from ..utils import associate, plainify
from .classes import Institution, Paper, PaperAuthor, PaperInfo


@dataclass
class PaperWorkingSet:
    current: Paper = None
    collected: list[PaperInfo] = field(default_factory=list)

    @classmethod
    def make(cls, p: PaperInfo):
        self = cls()
        self.add(p)
        return self

    def add(self, p: PaperInfo):
        self.collected.append(p)
        if self.current is None:
            self.current = p.paper
        else:
            self.current = merge(self.current, p.paper)


def qual(x, q):
    if isinstance(x, CommentProxy):
        x = x._obj
    return CommentProxy(x, q)


@ovld
def merge(x: object, y: object):
    return recurse(x, y, 0.0, 0.0)


@ovld(priority=10)
def merge(x: object, y: object, qx: Number, qy: Number):
    if qx <= -10:
        return y
    elif qy <= -10:
        return x
    else:
        return call_next(x, y, qx, qy)


@ovld
def merge(x: None, y: object, qx: Number, qy: Number):
    return y


@ovld(priority=0.1)
def merge(x: object, y: None, qx: Number, qy: Number):
    return x


@ovld
def merge(x: object, y: object, qx: Number, qy: Number):
    return x if qx > qy else y


@ovld(priority=1)
def merge(x: CommentProxy, y: object, qx: Number, qy: Number):
    qx = x._
    return qual(recurse(x._obj, y, qx, qy), max(qx, qy))


@ovld
def merge(x: object, y: CommentProxy, qx: Number, qy: Number):
    qy = y._
    return qual(recurse(x, y._obj, qx, qy), max(qx, qy))


@ovld
def merge(x: dict, y: dict, qx: Number, qy: Number):
    main, other, qx, qy = (x, y, qx, qy) if qx >= qy else (y, x, qy, qx)
    results = dict(other)
    for k, v in main.items():
        if k in other:
            results[k] = recurse(v, other[k], qx, qy)
        else:
            results[k] = v
    return results


@ovld
def merge(x: Dataclass, y: Dataclass, qx: Number, qy: Number):
    return type(x)(**recurse(vars(x), vars(y), qx, qy))


@ovld
def merge(x: list, y: list, qx: Number, qy: Number):
    main, other, qx, qy = (x, y, qx, qy) if qx >= qy else (y, x, qy, qx)
    if not main:
        return other
    elif not other:
        return main
    first = x[0]
    if isinstance(first, CommentProxy):
        first = first._obj
    return recurse(x, y, qx, qy, type(first))


@ovld
def merge(
    x: list, y: list, qx: Number, qy: Number, et: type[PaperAuthor] | type[Institution]
):
    results = []
    ass = associate(x, y, key=similarity, threshold=0.5)
    for x1, x2 in ass:
        merged = recurse(x1, x2, qx, qy) if x2 is not None else x1
        results.append(merged)
    return results


@ovld
def merge(x: list, y: list, qx: Number, qy: Number, et: type[object]):
    return x + [a for a in y if a not in x]


@ovld(priority=1)
def similarity(a: CommentProxy, b: object):
    return recurse(a._obj, b)


@ovld
def similarity(a: object, b: CommentProxy):
    return recurse(a, b._obj)


@ovld
def similarity(a: PaperAuthor, b: PaperAuthor):
    return similarity(a.display_name, b.display_name)


@ovld
def similarity(a: Institution, b: Institution):
    return similarity(a.name, b.name)


@ovld
def similarity(a: str, b: str):
    a = plainify(a)
    b = plainify(b)
    return SequenceMatcher(a=a, b=b).ratio()


def merge_all(entries):
    if not entries:
        return None
    result, *rest = entries
    for x in rest:
        result = merge(result, x)
    return result
