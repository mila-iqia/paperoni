import json
import re
import time
import urllib

import requests
import yaml
from bs4 import BeautifulSoup


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

    def __init__(self, url, format="text", **kwargs):
        super().__init__(**kwargs)
        self.base_url = url
        self.format = format

    def get_now(self, url, params=None):
        if params:
            params = urllib.parse.urlencode(params)
            url = f"https://{self.base_url}{url}?{params}"
        return readpage(url, format=self.format)


def readpage(url, format=None, **kwargs):
    resp = requests.get(url, **kwargs)
    content = resp.text

    match format:
        case "json":
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return None
        case "yaml":
            # Remove illegal characters
            content = re.sub(string=content, pattern=r"[\x80-\xff]", repl="")
            return yaml.safe_load(content)
        case "xml":
            return BeautifulSoup(content, features="xml")
        case "html":
            return BeautifulSoup(content, features="lxml")
        case _:
            return content
