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


#####################
# Operation helpers #
#####################


def release_status_order(release: Release):
    name = release.venue.name.lower()
    if release.status.lower() in ("submitted", "withdrawn", "rejected"):
        return -2
    elif (
        release.status == "preprint"
        or not name.strip()
        or name == "n/a"
        or "rxiv" in name
    ):
        return -1
    elif "workshop" in name:
        return 0
    else:
        return 1


def is_peer_reviewed_release(release: Release):
    return release_status_order(release) > 0


######################
# Defined operations #
######################


@flag_setter("peer-reviewed")
def peer_reviewed(p: Paper):
    return any(is_peer_reviewed_release(r) for r in p.releases)


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
