import re
import unicodedata
from collections import defaultdict

_uuid_tags = ["transient", "canonical"]


def asciiify(s):
    """Translate a string to pure ASCII, removing accents and the like.

    Non-ASCII characters that are not accented characters are removed.
    """
    norm = unicodedata.normalize("NFD", s)
    stripped = norm.encode("ASCII", "ignore")
    return stripped.decode("utf8")


def squash_text(txt):
    """Convert text to a sequence of lowercase characters and numbers.

    * Non-ASCII characters are converted to ASCII or dropped
    * Uppercase is converted to lowercase
    * All spaces and special characters are removed, only letters and numbers remain
    """
    txt = asciiify(txt).lower()
    return re.sub(pattern=r"[^a-z0-9]+", string=txt, repl="")


def tag_uuid(uuid, status):
    bit = _uuid_tags.index(status)
    nums = list(uuid)
    if bit:
        nums[0] = nums[0] | 128
    else:
        nums[0] = nums[0] & 127
    return bytes(nums)


def get_uuid_tag(uuid):
    return _uuid_tags[(uuid[0] & 128) >> 7]


def is_canonical_uuid(uuid):
    # return get_uuid_tag(uuid) == "canonical"
    return bool(uuid[0] & 128)


class EquivalenceGroups:
    def __init__(self):
        self.representatives = {}

    def equiv(self, a, b):
        ar = self.follow(a)
        br = self.follow(b)
        self.representatives[a] = ar
        self.representatives[b] = br
        if ar:
            self.representatives[b] = ar
            if br:
                self.representatives[br] = ar
        elif br:
            self.representatives[a] = br
        else:
            self.representatives[b] = a

    def equiv_all(self, ids):
        if not ids:
            return
        a, *rest = list(ids)
        for b in rest:
            self.equiv(a, b)

    def follow(self, a):
        if b := self.representatives.get(a, None):
            if a == b:
                return a
            self.representatives[a] = res = self.follow(b)
            return res
        else:
            return a

    def groups(self):
        for k in self.representatives:
            self.follow(k)
        results = defaultdict(set)
        for k, v in self.representatives.items():
            results[v].add(k)
        return results
