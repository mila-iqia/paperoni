import json
import os
import re
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cached_property
from pathlib import Path
from typing import Literal

import backoff
import chardet
import hishel
import httpx
import requests
from eventlet.timeout import Timeout
from fake_useragent import UserAgent
from hishel.httpx import AsyncCacheClient, SyncCacheClient
from outsight import send
from ovld import ovld
from requests import Session
from serieux import TaggedSubclass
from serieux.features.encrypt import Secret

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
    def generic(self, method, url, stream=False, **kwargs):
        raise NotImplementedError()

    def head(self, url, **kwargs):
        return self.generic("head", url, **kwargs)

    def get(self, url, **kwargs):
        return self.generic("get", url, **kwargs)

    def download(self, url, filename, **kwargs):
        """Download the given url into the given filename."""

        def iter_with_timeout(response, chunk_size: int, timeout: float):
            # Works with both httpx (iter_bytes) and requests (iter_content)
            iter_fn = getattr(response, "iter_bytes", None) or response.iter_content
            it = iter_fn(chunk_size=chunk_size)
            try:
                while True:
                    with Timeout(timeout):
                        yield next(it)
            except StopIteration:
                pass

        print(f"Downloading {url}")
        with self.generic("GET", url, stream=True, **kwargs) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 1024**2)
            sofar = 0
            with open(filename, "wb") as f:
                for chunk in iter_with_timeout(
                    r, chunk_size=max(total // 100, 1), timeout=5
                ):
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
            content = resp.text

            if cache_into:
                cache_into.parent.mkdir(parents=True, exist_ok=True)
                cache_into.write_text(content)

        return parse(content, format)

    @backoff.on_exception(
        backoff.expo,
        (httpx.HTTPError, requests.RequestException),
        giveup=_giveup,
        max_time=30,
        logger=None,
    )
    def read_retry(self, *args, **kwargs):
        return self.read(*args, **kwargs)

    # Async methods

    async def aread(
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
            resp = await self.aget(url, **kwargs)
            send(url=url, params=kwargs.get("params", {}), response=resp)
            resp.raise_for_status()
            content = resp.text

            if cache_into:
                cache_into.parent.mkdir(parents=True, exist_ok=True)
                cache_into.write_text(content)

        return parse(content, format)

    @backoff.on_exception(
        backoff.expo,
        (httpx.HTTPError, requests.RequestException),
        giveup=_giveup,
        max_time=30,
        logger=None,
    )
    async def aread_retry(self, *args, **kwargs):
        return await self.aread(*args, **kwargs)

    async def ageneric(self, method, url, stream=False, **kwargs):
        raise NotImplementedError()

    async def ahead(self, url, **kwargs):
        return await self.ageneric("head", url, **kwargs)

    async def aget(self, url, **kwargs):
        return await self.ageneric("get", url, **kwargs)

    async def adownload(self, url, filename, **kwargs):
        """Download the given url into the given filename (async)."""

        async def aiter_with_timeout(response, chunk_size: int, timeout: float):
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
                        with Timeout(timeout):
                            yield next(it)
                except StopIteration:
                    pass

        print(f"Downloading {url}")
        async with self.ageneric("GET", url, stream=True, **kwargs) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 1024**2)
            sofar = 0
            with open(filename, "wb") as f:
                async for chunk in aiter_with_timeout(
                    r, chunk_size=max(total // 100, 1), timeout=5
                ):
                    f.write(chunk)
                    f.flush()
                    sofar += len(chunk)
                    send(progress=(Path(url).name, sofar, total))
        print(f"Saved {filename}")


@dataclass
class HTTPXFetcher(Fetcher):
    user_agent: str = None
    timeout: int = 60

    def __post_init__(self):
        if self.user_agent is not None:
            try:
                self.user_agent = getattr(ua, self.user_agent)
            except AttributeError:
                pass

    @cached_property
    def client(self):
        return httpx.Client(follow_redirects=True, default_encoding=detect_encoding)

    @cached_property
    def aclient(self):
        return httpx.AsyncClient(follow_redirects=True, default_encoding=detect_encoding)

    def _prepare_kwargs(self, headers={}, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        headers = {k: v for k, v in headers.items() if v is not None}
        if self.user_agent:
            headers["User-Agent"] = self.user_agent
        if headers:
            kwargs["headers"] = headers
        return kwargs

    def generic(self, method, url, stream=False, headers={}, **kwargs):
        kwargs = self._prepare_kwargs(headers=headers, **kwargs)
        if stream:
            return self.client.stream(method.upper(), url, **kwargs)
        return getattr(self.client, method)(url, **kwargs)

    async def ageneric(self, method, url, stream=False, headers={}, **kwargs):
        kwargs = self._prepare_kwargs(headers=headers, **kwargs)
        if stream:
            return self.aclient.stream(method.upper(), url, **kwargs)
        return await getattr(self.aclient, method)(url, **kwargs)


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

    @cached_property
    def client(self):
        if not self.cache_path:
            return httpx.Client(follow_redirects=True, default_encoding=detect_encoding)
        ttl = self.expire_after.total_seconds() if self.expire_after else None
        storage = hishel.SyncSqliteStorage(
            database_path=str(self.cache_path) + ".db",
            default_ttl=ttl,
        )
        return SyncCacheClient(
            storage=storage,
            follow_redirects=True,
            default_encoding=detect_encoding,
            policy=self._cache_policy(),
        )

    @cached_property
    def aclient(self):
        if not self.cache_path:
            return httpx.AsyncClient(
                follow_redirects=True, default_encoding=detect_encoding
            )
        ttl = self.expire_after.total_seconds() if self.expire_after else None
        storage = hishel.AsyncSqliteStorage(
            database_path=str(self.cache_path) + ".db",
            default_ttl=ttl,
        )
        return AsyncCacheClient(
            storage=storage,
            follow_redirects=True,
            default_encoding=detect_encoding,
            policy=self._cache_policy(),
        )


@dataclass
class BannedFetcher(Fetcher):
    def generic(self, method, url, **kwargs):
        raise Exception(f"Will not try to fetch {url}")

    async def ageneric(self, method, url, **kwargs):
        raise Exception(f"Will not try to fetch {url}")


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

    def _prepare_kwargs(self, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        if self.user_agent:
            headers = kwargs.setdefault("headers", {})
            headers["UserAgent"] = headers["User-Agent"] = self.user_agent
        return kwargs

    def generic(self, method, url, stream=False, **kwargs):
        kwargs = self._prepare_kwargs(**kwargs)
        if stream:
            return self._stream_context(method, url, **kwargs)
        return getattr(self.session, method)(url, **kwargs)

    @contextmanager
    def _stream_context(self, method, url, **kwargs):
        kwargs["stream"] = True
        response = getattr(self.session, method.lower())(url, **kwargs)
        try:
            yield response
        finally:
            response.close()

    async def ageneric(self, method, url, stream=False, **kwargs):
        # Requests is sync-only, so we just call the sync version
        kwargs = self._prepare_kwargs(**kwargs)
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
class CloudFlareFetcher(RequestsFetcher):
    delay: int = 10

    @cached_property
    def session(self):
        import cloudscraper

        return cloudscraper.create_scraper(delay=self.delay)


@dataclass
class ScraperAPIFetcher(CachedFetcher):
    api_key: Secret[str] = None

    def _prepare_scraper_kwargs(self, url, **kwargs):
        assert self.api_key is not None
        payload = {
            "api_key": str(self.api_key),
            "url": url,
        }
        assert "params" not in kwargs
        kwargs["params"] = payload
        return kwargs

    def generic(self, method, url, **kwargs):
        kwargs = self._prepare_scraper_kwargs(url, **kwargs)
        return super().generic(method, "https://api.scraperapi.com/", **kwargs)

    async def ageneric(self, method, url, **kwargs):
        kwargs = self._prepare_scraper_kwargs(url, **kwargs)
        return await super().ageneric(method, "https://api.scraperapi.com/", **kwargs)


@dataclass
class SequenceFetcher(Fetcher):
    fetchers: list[TaggedSubclass[Fetcher]]

    def generic(self, method, url, **kwargs):
        for fetcher in self.fetchers:
            try:
                return fetcher.generic(method, url, **kwargs)
            except (httpx.HTTPError, requests.RequestException) as e:
                if e.response.status_code == 403:
                    continue
                else:
                    raise
        raise Exception(f"No fetcher could get {url}")

    async def ageneric(self, method, url, **kwargs):
        for fetcher in self.fetchers:
            try:
                return await fetcher.ageneric(method, url, **kwargs)
            except (httpx.HTTPError, requests.RequestException) as e:
                if e.response.status_code == 403:
                    continue
                else:
                    raise
        raise Exception(f"No fetcher could get {url}")


@dataclass
class RulesFetcher(Fetcher):
    rules: dict[re.Pattern, str]
    fetchers: dict[str, TaggedSubclass[Fetcher]]

    def _get_fetcher(self, url):
        for pattern, fetcher_key in self.rules.items():
            if pattern.search(url):
                return self.fetchers[fetcher_key]
        raise ValueError(f"No fetcher rule matches URL: {url}")

    def generic(self, method, url, **kwargs):
        return self._get_fetcher(url).generic(method, url, **kwargs)

    async def ageneric(self, method, url, **kwargs):
        return await self._get_fetcher(url).ageneric(method, url, **kwargs)
