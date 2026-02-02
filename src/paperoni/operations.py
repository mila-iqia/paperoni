from dataclasses import dataclass, replace
from typing import Callable

from .model import Paper


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
            if self.operation(p):
                if self.true_flag:
                    new_flags.add(self.true_flag)
                new_flags.discard(self.false_flag)
            else:
                if self.false_flag:
                    new_flags.add(self.false_flag)
                new_flags.discard(self.true_flag)
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
