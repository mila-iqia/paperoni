import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cached_property
from pathlib import Path
from typing import Literal

import backoff
import requests
import requests_cache
from eventlet.timeout import Timeout
from fake_useragent import UserAgent
from outsight import send
from ovld import ovld
from requests import HTTPError, Session
from requests.exceptions import RequestException
from serieux import TaggedSubclass
from serieux.features.encrypt import Secret

ua = UserAgent()


@ovld
def parse(content: str, format: Literal["json"]):
    return json.loads(content)


@ovld
def parse(content: str, format: Literal["yaml"]):
    import yaml

    # Some sources are polluted with invalid control/special characters,
    # probably because they were improperly encoded
    content = re.sub(
        string=content,
        pattern="[\x00-\x09]|[\x0b-\x0f]|[\x80-\x9f]",
        repl="",
    )
    return yaml.safe_load(content)


@ovld
def parse(content: str, format: Literal["xml"]):
    from bs4 import BeautifulSoup

    return BeautifulSoup(content, features="xml")


@ovld
def parse(content: str, format: Literal["html"]):
    from bs4 import BeautifulSoup

    return BeautifulSoup(content, features="lxml")


@ovld
def parse(content: str, format: Literal["txt"]):
    return content


def _giveup(exc):
    return getattr(exc, "response", None) is None or exc.response.status_code not in (
        403,
        429,
    )


class Fetcher:
    def generic(self, method, url, **kwargs):
        raise NotImplementedError()

    def head(self, url, **kwargs):
        return self.generic("head", url, **kwargs)

    def get(self, url, **kwargs):
        return self.generic("get", url, **kwargs)

    def download(self, url, filename, **kwargs):
        """Download the given url into the given filename."""

        def iter_with_timeout(r: requests.Response, chunk_size: int, timeout: float):
            it = r.iter_content(chunk_size=chunk_size)
            try:
                while True:
                    with Timeout(timeout):
                        yield next(it)
            except StopIteration:
                pass
            finally:
                it.close()

        print(f"Downloading {url}")
        r = self.get(url, stream=True, **kwargs)
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 1024**2)
        sofar = 0
        with open(filename, "wb") as f:
            for chunk in iter_with_timeout(r, chunk_size=max(total // 100, 1), timeout=5):
                f.write(chunk)
                f.flush()
                sofar += len(chunk)
                send(progress=(Path(url).name, sofar, total))
        print(f"Saved {filename}")

    def read(
        self, url, format=None, cache_into=None, cache_expiry: timedelta = None, **kwargs
    ):
        def is_cache_valid(path: Path, expiry: timedelta):
            if not path.exists():
                return False
            if expiry is None:
                return True
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            return (datetime.now() - mtime) < expiry

        if cache_into and is_cache_valid(cache_into, cache_expiry):
            content = cache_into.read_text()
        else:
            resp = self.get(url, **kwargs)
            send(url=url, params=kwargs.get("params", {}), response=resp)
            resp.raise_for_status()
            if resp.encoding == resp.apparent_encoding:
                content = resp.text
            else:
                content = resp.content.decode(resp.apparent_encoding, errors="ignore")

            if cache_into:
                cache_into.parent.mkdir(parents=True, exist_ok=True)
                cache_into.write_text(content)

        return parse(content, format)

    @backoff.on_exception(
        backoff.expo,
        RequestException,
        giveup=_giveup,
        max_time=30,
        logger=None,
    )
    def read_retry(self, *args, **kwargs):
        return self.read(*args, **kwargs)


@dataclass
class RequestsFetcher(Fetcher):
    user_agent: str = None
    timeout: int = 60

    def __post_init__(self):
        if self.user_agent is not None:
            try:
                self.user_agent = getattr(ua, self.user_agent)
            except AttributeError:
                pass

    @cached_property
    def session(self):
        return Session()

    def generic(self, method, url, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        if self.user_agent:
            headers = kwargs.setdefault("headers", {})
            headers["UserAgent"] = headers["User-Agent"] = self.user_agent
        return getattr(self.session, method)(url, **kwargs)


@dataclass
class CachedFetcher(RequestsFetcher):
    cache_path: Path = None
    expire_after: timedelta = None

    @cached_property
    def session(self):
        if not self.cache_path:
            return Session()
        exp = self.expire_after
        if exp is None:
            exp = requests_cache.NEVER_EXPIRE
        return requests_cache.CachedSession(self.cache_path, expire_after=exp)


@dataclass
class BannedFetcher(Fetcher):
    def generic(self, method, url, **kwargs):
        raise Exception(f"Will not try to fetch {url}")


@dataclass
class CloudFlareFetcher(RequestsFetcher):
    delay: int = 10

    @cached_property
    def session(self):
        import cloudscraper

        return cloudscraper.create_scraper(delay=self.delay)


@dataclass
class ScraperAPIFetcher(CachedFetcher):
    api_key: Secret[str] = None

    def generic(self, method, url, **kwargs):
        assert self.api_key is not None
        payload = {
            "api_key": str(self.api_key),
            "url": url,
        }
        assert "params" not in kwargs
        kwargs["params"] = payload
        return super().generic(method, "https://api.scraperapi.com/", **kwargs)


@dataclass
class SequenceFetcher(Fetcher):
    fetchers: list[TaggedSubclass[Fetcher]]

    def generic(self, method, url, **kwargs):
        for fetcher in self.fetchers:
            try:
                return fetcher.generic(method, url, **kwargs)
            except HTTPError as e:
                if e.response.status_code == 403:
                    continue
                else:
                    raise
        raise Exception(f"No fetcher could get {url}")


@dataclass
class RulesFetcher(Fetcher):
    rules: dict[re.Pattern, str]
    fetchers: dict[str, TaggedSubclass[Fetcher]]

    def generic(self, method, url, **kwargs):
        for pattern, fetcher_key in self.rules.items():
            if pattern.search(url):
                fetcher = self.fetchers[fetcher_key]
                return fetcher.generic(method, url, **kwargs)
        raise ValueError(f"No fetcher rule matches URL: {url}")
