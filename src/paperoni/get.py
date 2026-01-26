import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import cached_property
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import chardet
import hishel
import httpx
import requests
from fake_useragent import UserAgent
from hishel.httpx import AsyncCacheClient
from outsight import send
from ovld import ovld
from requests import Session
from serieux import TaggedSubclass
from serieux.features.encrypt import Secret
from tenacity import retry, stop_after_delay, wait_exponential, wait_random

ERRORS = (httpx.HTTPStatusError, requests.RequestException)
ua = UserAgent()


def detect_encoding(content):
    return chardet.detect(content).get("encoding")


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
    response = getattr(exc, "response", None)
    if response is None:
        return True
    status_code = getattr(response, "status_code", None)
    if status_code is None:
        return True
    return status_code not in (403, 429)


class Fetcher:
    async def generic(self, method, url, stream=False, **kwargs):
        raise NotImplementedError()

    async def head(self, url, **kwargs):
        return await self.generic("head", url, **kwargs)

    async def get(self, url, **kwargs):
        return await self.generic("get", url, **kwargs)

    async def download(self, url, filename, **kwargs):
        """Download the given url into the given filename (async)."""

        async def aiter(response, chunk_size: int):
            # Works with httpx async (aiter_bytes)
            iter_fn = getattr(response, "aiter_bytes", None)
            if iter_fn:
                async for chunk in iter_fn(chunk_size=chunk_size):
                    yield chunk
            else:
                # Fallback for sync-style responses
                iter_fn = getattr(response, "iter_bytes", None) or response.iter_content
                it = iter_fn(chunk_size=chunk_size)
                try:
                    while True:
                        yield next(it)
                except StopIteration:
                    pass

        print(f"Downloading {url}")
        async with await self.get(url, stream=True, **kwargs) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 1024**2)
            sofar = 0
            with open(filename, "wb") as f:
                async for chunk in aiter(r, chunk_size=max(total // 100, 1)):
                    f.write(chunk)
                    f.flush()
                    sofar += len(chunk)
                    send(progress=(Path(url).name, sofar, total))
        print(f"Saved {filename}")

    async def read(
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
            resp = await self.get(url, **kwargs)
            send(url=url, params=kwargs.get("params", {}), response=resp)
            resp.raise_for_status()
            content = resp.text

            if cache_into:
                cache_into.parent.mkdir(parents=True, exist_ok=True)
                cache_into.write_text(content)

        return parse(content, format)

    @retry(
        wait=wait_exponential(multiplier=1, exp_base=2) + wait_random(0, 0.5),
        stop=stop_after_delay(30),
        retry=lambda retry_state: not _giveup(retry_state.outcome.exception()),
        reraise=True,
    )
    async def read_retry(self, *args, **kwargs):
        return await self.read(*args, **kwargs)


@dataclass
class HTTPXFetcher(Fetcher):
    user_agent: str = None
    timeout: int = 60

    # [serieux: ignore]
    _client: httpx.AsyncClient = None
    # [serieux: ignore]
    _client_loop = None

    def __post_init__(self):
        if self.user_agent is not None:
            try:
                self.user_agent = getattr(ua, self.user_agent)
            except AttributeError:
                pass

    @property
    def client(self):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._client is None or self._client_loop is not loop:
            self._client = httpx.AsyncClient(
                follow_redirects=True, default_encoding=detect_encoding
            )
            self._client_loop = loop
        return self._client

    async def generic(self, method, url, stream=False, headers={}, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        headers = {k: v for k, v in headers.items() if v is not None}
        if self.user_agent:
            headers["User-Agent"] = self.user_agent
        if headers:
            kwargs["headers"] = headers
        if stream:
            return self.client.stream(method.upper(), url, **kwargs)
        return await getattr(self.client, method)(url, **kwargs)


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

    async def generic(self, method, url, stream=False, **kwargs):
        # Requests is sync-only, so we just call the sync version
        kwargs.setdefault("timeout", self.timeout)
        if self.user_agent:
            headers = kwargs.setdefault("headers", {})
            headers["UserAgent"] = headers["User-Agent"] = self.user_agent
        if stream:
            return self._astream_context(method, url, **kwargs)
        return getattr(self.session, method)(url, **kwargs)

    @asynccontextmanager
    async def _astream_context(self, method, url, **kwargs):
        kwargs["stream"] = True
        response = getattr(self.session, method.lower())(url, **kwargs)
        try:
            yield response
        finally:
            response.close()


@dataclass
class CachedFetcher(HTTPXFetcher):
    cache_path: Path = None
    expire_after: timedelta = None

    def _cache_policy(self):
        return hishel.SpecificationPolicy(
            cache_options=hishel.CacheOptions(
                shared=False,
                supported_methods=["GET", "HEAD", "POST"],
                allow_stale=True,
            )
        )

    @property
    def client(self):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._client is None or self._client_loop is not loop:
            if not self.cache_path:
                self._client = httpx.AsyncClient(
                    follow_redirects=True, default_encoding=detect_encoding
                )
            else:
                ttl = self.expire_after.total_seconds() if self.expire_after else None
                storage = hishel.AsyncSqliteStorage(
                    database_path=str(self.cache_path) + ".db",
                    default_ttl=ttl,
                )
                self._client = AsyncCacheClient(
                    storage=storage,
                    follow_redirects=True,
                    default_encoding=detect_encoding,
                    policy=self._cache_policy(),
                )
            self._client_loop = loop
        return self._client


@dataclass
class BannedFetcher(Fetcher):
    async def generic(self, method, url, **kwargs):
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

    async def generic(self, method, url, **kwargs):
        assert self.api_key is not None
        payload = {
            "api_key": str(self.api_key),
            "url": url,
        }
        assert "params" not in kwargs
        kwargs["params"] = payload
        return await super().generic(method, "https://api.scraperapi.com/", **kwargs)


@dataclass
class SequenceFetcher(Fetcher):
    fetchers: list[TaggedSubclass[Fetcher]]

    async def generic(self, method, url, **kwargs):
        for fetcher in self.fetchers:
            try:
                return await fetcher.generic(method, url, **kwargs)
            except ERRORS as e:
                if e.response.status_code == 403:
                    continue
                else:
                    raise
        raise Exception(f"No fetcher could get {url}")


@dataclass
class RulesFetcher(Fetcher):
    rules: dict[re.Pattern, str]
    fetchers: dict[str, TaggedSubclass[Fetcher]]
    simultaneous: dict[str, int] = field(default_factory=dict)

    # [serieux: ignore]
    _semaphores: dict[str, asyncio.Semaphore] = field(default_factory=dict, repr=False)

    def _get_semaphore(self, hostname: str) -> asyncio.Semaphore | None:
        """Get or create a semaphore for the given hostname."""
        if hostname not in self._semaphores:
            limit = self.simultaneous.get(hostname, None) or self.simultaneous.get(
                "*", -1
            )
            if limit == -1:
                return None
            self._semaphores[hostname] = asyncio.Semaphore(limit)

        return self._semaphores[hostname]

    async def generic(self, method, url, **kwargs):
        for pattern, fetcher_key in self.rules.items():
            if pattern.search(url):
                f = self.fetchers[fetcher_key]
                hostname = urlparse(url).hostname or ""
                if (semaphore := self._get_semaphore(hostname)) is not None:
                    async with semaphore:
                        return await f.generic(method, url, **kwargs)
                else:
                    return await f.generic(method, url, **kwargs)
        raise ValueError(f"No fetcher rule matches URL: {url}")
