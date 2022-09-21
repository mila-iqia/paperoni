import http.client
import json
import time
import urllib
from hashlib import md5
from pathlib import Path

from bs4 import BeautifulSoup

from ..config import load_config


class RateLimitedAcquirer:
    """Acquire resources while respecting a certain rate limit.

    For example, if an API allows 100 requests per minute, you can set
    ``delay=60/100, bulk=1`` to space 100 requests evenly each minute,
    or ``delay=60, bulk=100`` to do 100 requests without delay, then wait a
    minute, do 100 more, etc. Note that the second method might break the
    limit if the program is invoked more than once in a short time.

    Each call to ``get()`` is a single request.

    RateLimitedAcquirer is somewhat dumb and won't take into account
    time spent by the rest of the program.

    RateLimitedAcquirer is synchronous.

    Arguments:
        delay: The delay, in seconds, to respect between groups of requests.
        bulk: The number of requests in a group, to perform without delay.
        first_bulk: The number of requests to perform without delay,
            the first time.
    """

    def __init__(self, *, delay=0, bulk=1, first_bulk=None):
        self.delay = delay
        self.bulk = bulk
        self.first_bulk = first_bulk or bulk
        self.bulks = 0
        self.count = 0

    def get(self, url, **kwargs):
        """Get the resource while respecting the rate limit."""
        bulk = self.first_bulk if self.bulks == 0 else self.bulk
        if self.count >= bulk:
            time.sleep(self.delay)
            self.count = 0
            self.bulks += 1
        self.count += 1
        return self.get_now(url, **kwargs)

    def get_now(self, url):
        raise NotImplementedError()


class HTTPSAcquirer(RateLimitedAcquirer):
    """Acquire resources from an HTTPS connection."""

    def __init__(self, url, format="text", cache=True, **kwargs):
        super().__init__(**kwargs)
        self.base_url = url
        self.format = format
        self.cache = cache

    def get_now(self, url, params=None):
        if params:
            params = urllib.parse.urlencode(params)
            url = f"https://{self.base_url}{url}?{params}"
        return readpage(url, format=self.format, cache=self.cache)


def readpage(url, format=None, cache=True):
    cfg = load_config()
    domain = url.split("/")[2]
    filename = (
        Path(cfg.cache_root)
        / "https"
        / domain
        / md5(url.encode("utf8")).hexdigest()
    )
    if cache and filename.exists():
        with open(filename) as f:
            content = f.read()
        cache = False  # This will avoid writing the file again
    else:
        conn = http.client.HTTPSConnection(domain)
        conn.request("GET", url)
        resp = conn.getresponse()
        if resp.status == 301:
            loc = resp.info().get_all("Location")[0]
            content = readpage(loc)
        else:
            content = resp.read()
            resp.close()

    if cache:
        filename.parent.mkdir(parents=True, exist_ok=True)
        with open(filename, "w") as f:
            f.write(content.decode("utf8"))
            f.close()

    match format:
        case "json":
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return None
        case "xml":
            return BeautifulSoup(content, features="xml")
        case "html":
            return BeautifulSoup(content, features="html")
        case _:
            return content
