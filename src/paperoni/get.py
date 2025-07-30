import json
import re
from dataclasses import dataclass
from datetime import timedelta
from functools import cached_property
from pathlib import Path
from typing import Literal

import backoff
import requests_cache
from fake_useragent import UserAgent
from ovld import ovld
from requests import Session
from requests.exceptions import RequestException
from serieux import TaggedSubclass

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


class Fetcher:
    def get(self, url, **kwargs):
        raise NotImplementedError()

    def read(self, url, format=None, cache_into=None, **kwargs):
        if cache_into and cache_into.exists():
            content = cache_into.read_text()
        else:
            resp = self.get(url, **kwargs)
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
        giveup=lambda exc: exc.response.status_code not in (403, 429),
        max_time=10,
    )
    def read_retry(self, *args, **kwargs):
        return self.read(*args, **kwargs)


@dataclass
class RequestsFetcher(Fetcher):
    user_agent: str = None

    def __post_init__(self):
        if self.user_agent is not None:
            try:
                self.user_agent = getattr(ua, self.user_agent)
            except AttributeError:
                pass

    @cached_property
    def session(self):
        return Session()

    def get(self, url, **kwargs):
        if self.user_agent:
            headers = kwargs.setdefault("headers", {})
            headers["UserAgent"] = headers["User-Agent"] = self.user_agent
        return self.session.get(url, **kwargs)


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
    def get(self, url, **kwargs):
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
    api_key: str = None

    def get(self, url, **kwargs):
        assert self.api_key is not None
        payload = {
            "api_key": str(self.api_key),
            "url": url,
        }
        assert "params" not in kwargs
        kwargs["params"] = payload
        return super().get("https://api.scraperapi.com/", **kwargs)


@dataclass
class SequenceFetcher(Fetcher):
    fetchers: list[Fetcher]

    def get(self, url, **kwargs):
        exceptions = []
        for fetcher in self.fetchers:
            try:
                return fetcher.get(url, **kwargs)
            except Exception as e:
                exceptions.append(e)
                continue
        raise ExceptionGroup("All fetchers failed", exceptions)


@dataclass
class RulesFetcher(Fetcher):
    rules: dict[re.Pattern, str]
    fetchers: dict[str, TaggedSubclass[Fetcher]]

    def get(self, url, **kwargs):
        for pattern, fetcher_key in self.rules.items():
            if pattern.search(url):
                fetcher = self.fetchers[fetcher_key]
                return fetcher.get(url, **kwargs)
        raise ValueError(f"No fetcher rule matches URL: {url}")
