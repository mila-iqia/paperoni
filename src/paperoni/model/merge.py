from dataclasses import dataclass
from difflib import SequenceMatcher
from numbers import Number
from typing import Any

from ovld import Dataclass, Medley, call_next, ovld, recurse
from ovld.dependent import HasKey
from serieux import Context, Serieux
from wrapt import ObjectProxy

from ..model.classes import Institution, PaperAuthor
from ..utils import associate, plainify


@dataclass
class Annotations:
    quality: float


class AugmentedProxy(ObjectProxy):
    def __init__(self, wrapped, aug):
        super().__init__(wrapped)
        self._self_ann = aug

    @property
    def _(self):
        return self._self_ann

    def __repr__(self):
        return f"<{self.__wrapped__!r}>"


@Serieux.extend
class HandleProxy(Medley):
    @ovld(priority=1)
    def serialize(self, t: Any, obj: AugmentedProxy, ctx: Context):
        return {
            "$ann": recurse(Annotations, obj._self_ann, ctx),
            "$value": recurse(t, obj.__wrapped__, ctx),
        }

    @ovld(priority=1)
    def deserialize(self, t: Any, obj: HasKey["$ann"], ctx: Context):
        return AugmentedProxy(
            recurse(t, obj["$value"], ctx),
            recurse(Annotations, obj["$ann"], ctx),
        )


def qual(x, q):
    if isinstance(x, AugmentedProxy):
        x = x.__wrapped__
    return AugmentedProxy(x, Annotations(quality=q))


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
def merge(x: object, y: object, qx: Number, qy: Number):
    print("~", x, y, qx, qy)
    return x if qx > qy else y


@ovld(priority=1)
def merge(x: AugmentedProxy, y: object, qx: Number, qy: Number):
    qx = x._.quality
    return qual(recurse(x.__wrapped__, y, qx, qy), max(qx, qy))


@ovld
def merge(x: object, y: AugmentedProxy, qx: Number, qy: Number):
    qy = y._.quality
    return qual(recurse(x, y.__wrapped__, qx, qy), max(qx, qy))


@ovld
def merge(x: dict, y: dict, qx: Number, qy: Number):
    main, other, qx, qy = (x, y, qx, qy) if qx >= qy else (y, x, qy, qx)
    results = dict(other)
    for k, v in main.items():
        if k in other:
            results[k] = recurse(v, other[k], qx, qy)
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
    if isinstance(first, AugmentedProxy):
        first = first.__wrapped__
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
def similarity(a: AugmentedProxy, b: object):
    return recurse(a.__wrapped__, b)


@ovld
def similarity(a: object, b: AugmentedProxy):
    return recurse(a, b.__wrapped__)


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
