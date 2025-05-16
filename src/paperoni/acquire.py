import json
import re
import urllib

import backoff
import requests


class HTTPSAcquirer:
    """Acquire resources from an HTTPS connection."""

    def __init__(self, url, format="text"):
        self.base_url = url
        self.format = format

    @backoff.on_exception(
        backoff.expo,
        requests.exceptions.RequestException,
        giveup=lambda exc: exc.response.status_code == 404,
        max_time=5,
    )
    def get(self, url, params=None, headers={}):
        if params:
            params = urllib.parse.urlencode(params)
            url = f"https://{self.base_url}{url}?{params}"
        else:
            url = f"https://{self.base_url}{url}"
        return readpage(url, format=self.format, headers=headers)


def readpage(url, format=None, cache_into=None, **kwargs):
    if cache_into and cache_into.exists():
        content = cache_into.read_text()

    else:
        resp = requests.get(url, **kwargs)
        resp.raise_for_status()
        if resp.encoding == resp.apparent_encoding:
            content = resp.text
        else:
            content = resp.content.decode(resp.apparent_encoding, errors="ignore")

        if cache_into:
            cache_into.parent.mkdir(parents=True, exist_ok=True)
            cache_into.write_text(content)

    match format:
        case "json":
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return None
        case "yaml":
            import yaml

            # Some sources are polluted with invalid control/special characters,
            # probably because they were improperly encoded
            content = re.sub(
                string=content,
                pattern="[\x00-\x09]|[\x0b-\x0f]|[\x80-\x9f]",
                repl="",
            )
            return yaml.safe_load(content)
        case "xml":
            from bs4 import BeautifulSoup

            return BeautifulSoup(resp.content, features="xml")
        case "html":
            from bs4 import BeautifulSoup

            return BeautifulSoup(content, features="lxml")
        case _:
            return content
