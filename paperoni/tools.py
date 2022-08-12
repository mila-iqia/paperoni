import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher

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


def similarity(s1, s2):
    def junk(x):
        return x in ".-"

    return SequenceMatcher(junk, s1, s2).ratio()


def extract_date(txt):
    from .model import DatePrecision

    if not isinstance(txt, str):
        return None

    months = [
        "Jan-uary",
        "Feb-ruary",
        "Mar-ch",
        "Apr-il",
        "May-",
        "Jun-e",
        "Jul-y",
        "Aug-ust",
        "Sep-tember",
        "Oct-ober",
        "Nov-ember",
        "Dec-ember",
    ]
    months = [m.split("-") for m in months]
    stems = [a.lower() for a, b in months]
    months = [(f"{a}(?:{b})?" if b else a) for a, b in months]
    month = "|".join(months)

    patterns = {
        rf"({month}) ([0-9]{{1,2}}) *- *(?:{month}) [0-9]{{1,2}}[, ]+([0-9]{{4}})": (
            "m",
            "d",
            "y",
        ),
        rf"({month}) ([0-9]{{1,2}}) *- *[0-9]{{1,2}}[, ]+([0-9]{{4}})": (
            "m",
            "d",
            "y",
        ),
        rf"({month}) ([0-9]{{1,2}})[, ]+([0-9]{{4}})": ("m", "d", "y"),
        rf"([0-9]{{1,2}}) *- *[0-9]{{1,2}}[ ,]+({month})[, ]+([0-9]{{4}})": (
            "d",
            "m",
            "y",
        ),
        rf"([0-9]{{1,2}})[ ,]+({month})[, ]+([0-9]{{4}})": ("d", "m", "y"),
        rf"({month}) +([0-9]{{4}})": ("m", "y"),
    }

    for pattern, parts in patterns.items():
        if m := re.search(pattern=pattern, string=txt, flags=re.IGNORECASE):
            results = {k: m.groups()[i] for i, k in enumerate(parts)}
            precision = DatePrecision.day
            if "d" not in results:
                results.setdefault("d", 1)
                precision = DatePrecision.month
            return {
                "date": datetime(
                    int(results["y"]),
                    stems.index(results["m"].lower()[:3]) + 1,
                    int(results["d"]),
                ),
                "date_precision": precision,
            }
    else:
        return None


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
        self.names = {}
        self.classes = {}

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

    def equiv_all(self, ids, cls=None, under=None):
        if not ids:
            return
        a, *rest = list(ids)
        for b in rest:
            self.equiv(a, b)
        for x in ids:
            self.names[x] = under
            self.classes[x] = cls

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

    def __iter__(self):
        for main, ids in self.groups().items():
            assert len(ids) > 1
            print(f"Merging {len(ids)} IDs for {self.names[main]}")
            yield self.classes[main](ids=ids)
