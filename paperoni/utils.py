import functools
import inspect
import itertools
import re
import unicodedata
from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from difflib import SequenceMatcher

from giving import give
from unidecode import unidecode

_uuid_tags = ["transient", "canonical"]


class QueryError(Exception):
    pass


class MutuallyExclusiveError(RuntimeError):
    """Exception raised when mutually exclusive parameters are used in queries."""

    def __init__(self, *args):
        self.args = args

    def __str__(self):
        return "Mutually exclusive parameters: " + " vs ".join(
            self._param_to_str(arg) for arg in self.args
        )

    def _param_to_str(self, param):
        return param if isinstance(param, str) else f"({', '.join(param)})"


def asciiify(s: str) -> str:
    """Translate a string to pure ASCII, removing accents and the like.

    Non-ASCII characters that are not accented characters are removed.
    """
    norm = unicodedata.normalize("NFD", s)
    stripped = norm.encode("ASCII", "ignore")
    return stripped.decode("utf8")


def squash_text(txt: str) -> str:
    """Convert text to a sequence of lowercase characters and numbers.

    * Non-ASCII characters are converted to ASCII or dropped
    * Uppercase is converted to lowercase
    * All spaces and special characters are removed, only letters and numbers remain
    """
    txt = asciiify(txt).lower()
    return re.sub(pattern=r"[^a-z0-9]+", string=txt, repl="")


url_extractors = {
    r"https?://[a-z.]*arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]+).*": "arxiv",
    r"https?://[a-z.]*arxiv-vanity\.com/papers/([0-9]{4}\.[0-9]+).*": "arxiv",
    r"https?://(?:[^/]*)arxiv(?:[^/]*)\.cornell\.edu/abs/([0-9]{4}\.[0-9]+).*": "arxiv",
    r"https?://scirate\.com/arxiv/([0-9]{4}\.[0-9]+).*": "arxiv",
    r"https?://pubmed\.ncbi\.nlm\.nih\.gov/([^/]*)/": "pubmed",
    r"https?://www\.ncbi\.nlm\.nih\.gov/pubmed/([^/]*)": "pubmed",
    r"https?://www\.ncbi\.nlm\.nih\.gov/pmc/articles/([^/]*)": "pmc",
    r"https?://europepmc.org/article/PMC/([^/]*)": "pmc",
    r"https?://(?:dx\.)?doi\.org/(.*)": "doi",
    r"https?://(?:www\.)?openreview\.net/(?:pdf\?|forum\?)id=(.*)": "openreview",
    r"https?://dblp.uni-trier.de/db/([^/]+)/([^/]+)/[^/]+\.html#(.*)": "dblp",
}


def url_to_id(url: str) -> tuple[str, str]:
    """Return an ID from a URL.

    * Given a link to an arxiv abstract or pdf, return ``("arxiv", arxiv_id)``
    * Given a DOI link, return ``("doi", the_doi)``
    * etc.

    See the ``url_extractors`` dictionary for the regexps and corresponding ID type.
    ``url_to_id`` tries each extractor in order.
    """
    for pattern, key in url_extractors.items():
        if m := re.match(pattern, url):
            lnk = "/".join(m.groups())
            return (key, lnk)
    return None


def canonicalize_links(links: dict[str, str]) -> dict[str, str]:
    """Reduce a list of URL-based links to more precise types of links.

    For example:

    >>> canonicalize_links([{"type": "html", "link": "https://arxiv.org/pdf/1234.5678"}])
    [{"type": "arxiv", "link": "1234.5678"}]
    """
    links = {
        url_to_id(url := link["link"]) or (link["type"], url) for link in links
    }
    return [{"type": typ, "link": lnk} for typ, lnk in links]


def similarity(s1, s2):
    s1 = plainify(s1)
    s2 = plainify(s2)
    return SequenceMatcher(a=s1, b=s2).ratio()


def associate(names1, names2):
    if names1 == names2:
        return [(i, i) for i in range(len(names1))]

    matrix = [
        (similarity(n1, n2), i, j)
        for i, n1 in enumerate(names1)
        for j, n2 in enumerate(names2)
    ]
    results = []
    to_process1 = set(range(len(names1)))
    to_process2 = set(range(len(names2)))
    matrix.sort(reverse=True)
    for sim, i, j in matrix:
        if i not in to_process1 or j not in to_process2:
            continue
        elif sim >= 0.7 or (sim >= 0.4 and consistent([names1[i], names2[j]])):
            to_process1.discard(i)
            to_process2.discard(j)
            results.append((i, j))
        else:
            break
    results += [(i, None) for i in to_process1]
    results += [(None, j) for j in to_process2]
    results.sort(key=lambda x: x[1] if x[0] is None else x[0])
    return results


def extract_date(txt: str) -> dict | None:
    from .model import DatePrecision

    if isinstance(txt, int):
        return {
            "date": datetime(txt, 1, 1),
            "date_precision": DatePrecision.year,
        }

    if not isinstance(txt, str):
        return None

    # The dash just separates the 3-letter abbreviation from the rest of the month,
    # it is split immediately after that
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
    months = [(f"{a}(?:{b})?\\.?" if b else a) for a, b in months]
    month = "|".join(
        months
    )  # This is a regexp like "Jan(uary)?|Feb(ruary)?|..."

    patterns = {
        # Jan 3-Jan 7 2020
        rf"({month}) ([0-9]{{1,2}}) *- *(?:{month}) [0-9]{{1,2}}[, ]+([0-9]{{4}})": (
            "m",
            "d",
            "y",
        ),
        # Jan 3-7 2020
        rf"({month}) ([0-9]{{1,2}}) *- *[0-9]{{1,2}}[, ]+([0-9]{{4}})": (
            "m",
            "d",
            "y",
        ),
        # Jan 3 2020
        rf"({month}) ?([0-9]{{1,2}})[, ]+([0-9]{{4}})": ("m", "d", "y"),
        # 3-7 Jan 2020
        rf"([0-9]{{1,2}}) *- *[0-9]{{1,2}}[ ,]+({month})[, ]+([0-9]{{4}})": (
            "d",
            "m",
            "y",
        ),
        # 3 Jan 2020
        rf"([0-9]{{1,2}})[ ,]+({month})[, ]+([0-9]{{4}})": ("d", "m", "y"),
        # Jan 2020
        rf"({month}) +([0-9]{{4}})": ("m", "y"),
        # 2020 Jan 3
        rf"([0-9]{{4}}) ({month}) ([0-9]{{1,2}})": ("y", "m", "d"),
        # 2020 Jan
        rf"([0-9]{{4}}) ({month})": ("y", "m"),
        r"([0-9]{4})": ("y",),
    }

    for pattern, parts in patterns.items():
        if m := re.search(pattern=pattern, string=txt, flags=re.IGNORECASE):
            results = {k: m.groups()[i] for i, k in enumerate(parts)}
            precision = DatePrecision.day
            if "d" not in results:
                results.setdefault("d", 1)
                precision = DatePrecision.month
            if "m" not in results:
                results.setdefault("m", "Jan")
                precision = DatePrecision.year
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
        self.representatives[b] = ar
        self.representatives[br] = ar

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


def keyword_decorator(deco):
    """Wrap a decorator to optionally takes keyword arguments."""

    @functools.wraps(deco)
    def new_deco(fn=None, **kwargs):
        if fn is None:

            @functools.wraps(deco)
            def newer_deco(fn):
                return deco(fn, **kwargs)

            return newer_deco
        else:
            return deco(fn, **kwargs)

    return new_deco


###################
# Paper utilities #
###################


def status_order(release):
    name = release.venue.name.lower()
    if release.status in ("submitted", "withdrawn", "rejected"):
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


def peer_reviewed_release(release):
    return status_order(release) > 0


def sort_releases(releases):
    releases = [(release, status_order(release)) for release in releases]
    releases.sort(key=lambda entry: -entry[1])
    return releases


link_generators = {
    "arxiv": {
        "abstract": "https://arxiv.org/abs/{}",
        "pdf": "https://arxiv.org/pdf/{}.pdf",
    },
    "pubmed": {
        "abstract": "https://pubmed.ncbi.nlm.nih.gov/{}",
    },
    "pmc": {
        "abstract": "https://www.ncbi.nlm.nih.gov/pmc/articles/{}",
    },
    "doi": {
        "abstract": "https://doi.org/{}",
    },
    "openreview": {
        "abstract": "https://openreview.net/forum?id={}",
        "pdf": "https://openreview.net/pdf?id={}",
    },
    "mlr": {
        "abstract": "https://proceedings.mlr.press/v{}.html",
    },
    "dblp": {"abstract": "https://dblp.uni-trier.de/rec/{}"},
    "semantic_scholar": {
        "abstract": "https://www.semanticscholar.org/paper/{}"
    },
    "openalex": {
        "abstract": "https://openalex.org/{}",
    },
    # Placeholder to parse ORCID links, although those are not exactly paper links
    "orcid": {"abstract": "https://orcid.org/{}"},
}


def expand_links_dict(links):
    pref = [
        "html.official",
        "pdf.official",
        "doi.abstract",
        "mlr.abstract",
        "mlr.pdf",
        "openreview.abstract",
        "openreview.pdf",
        "arxiv.abstract",
        "arxiv.pdf",
        "pubmed.abstract",
        "pmc.abstract",
        "dblp.abstract",
        "pdf",
        "html",
        "semantic_scholar.abstract",
        "corpusid",
        "mag",
        "xml",
        "patent",
        "unknown",
        "unknown_",
    ]
    results = []
    for link in links:
        if link.type in link_generators:
            results.extend(
                {
                    "type": f"{link.type}.{kind}",
                    "link": link.link,
                    "url": url.format(link.link),
                }
                for kind, url in link_generators[link.type].items()
            )
        else:
            results.append({"type": link.type, "link": link.link})
    results.sort(
        key=lambda dct: pref.index(dct["type"])
        if dct["type"] in pref
        else 1_000
    )
    return results


def quality_int(quality_tuple):
    if isinstance(quality_tuple, int):
        return quality_tuple
    qual = quality_tuple + (0,) * (4 - len(quality_tuple))
    result = 0
    for x in qual:
        result <<= 8
        result |= int(x * 255) & 255
    return result


def plainify(name):
    name = unidecode(name).lower()
    name = re.sub(string=name, pattern="[()-]", repl=" ")
    name = re.sub(string=name, pattern="['.]", repl="")
    return name


def consistent_pair(name1, name2):
    def bag(name):
        name = plainify(name)
        bag = set(name.split())
        return bag | {word[0] for word in bag}

    b1 = bag(name1)
    b2 = bag(name2)
    b1x = b1 - b2
    b2x = b2 - b1
    consistent = not (b1x and b2x)
    return consistent


def consistent(aliases):
    return all(
        consistent_pair(n1, n2)
        for n1, n2 in itertools.product(aliases, aliases)
    )


def best_name(main_name, aliases):
    if not consistent(aliases):
        return main_name

    def penalty(name):
        return (
            re.match(string=name, pattern=r"^\w[. ]") is not None,
            abs(20 - len(name)),
        )

    return min(aliases, key=penalty)


####################
# Proxying objects #
####################


class Proxy:
    def __init__(self, base, **replacements):
        self._proxy_base = base
        self._proxy_replacements = replacements

    def __getattribute__(self, attr):
        if attr.startswith("_proxy_"):
            return object.__getattribute__(self, attr)
        if attr in self._proxy_replacements:
            return self._proxy_replacements[attr]
        else:
            return getattr(self._proxy_base, attr)


def conditional_proxy(base, **replacements):
    if any(v == [] or v is None for v in replacements.values()):
        return None

    if isinstance(base, Proxy):
        base = base._proxy_base
        replacements = {**base._proxy_replacements, **replacements}

    return Proxy(base, **replacements)


##############################
# covguard-related utilities #
##############################


currently_doing = ContextVar("doing", default=None)


class Doing:
    """Usage: ``with Doing(method="refine", title="blah"): ...``"""

    def __init__(self, **description):
        self.description = description

    def __enter__(self):
        self.token = currently_doing.set(self)
        return self

    def __exit__(self, *_):
        currently_doing.reset(self.token)


@contextmanager
def covguard(**more_keys):
    """Propagate a message about coverage of a block of code.

    Use ``with covguard() ...`` to wrap some piece of code that is not
    covered by tests. If some use case triggers the covered code, information
    will be propagated about what we are doing, to help craft a test case.
    """
    info = inspect.getframeinfo(inspect.stack()[2][0])
    doing = currently_doing.get()
    kw = doing.description if doing else {}
    if doing:
        give(
            situation="cover",
            location=f"{info.filename}:{info.lineno}",
            **kw,
            **more_keys,
        )
    yield


@keyword_decorator
def covguard_fn(fn, **keys):
    """Apply covguard to the execution of the function."""

    @functools.wraps(fn)
    def deco(*args, **kwargs):
        with covguard(**keys):
            return fn(*args, **kwargs)

    return deco
