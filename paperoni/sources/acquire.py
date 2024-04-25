import json
import re
import urllib

import backoff
import requests
import yaml
from bs4 import BeautifulSoup


class HTTPSAcquirer:
    """Acquire resources from an HTTPS connection."""

    def __init__(self, url, format="text"):
        self.base_url = url
        self.format = format

    @backoff.on_exception(
        backoff.expo,
        requests.exceptions.RequestException,
    )
    def get(self, url, params=None, headers={}):
        if params:
            params = urllib.parse.urlencode(params)
            url = f"https://{self.base_url}{url}?{params}"
        else:
            url = f"https://{self.base_url}{url}"
        return readpage(url, format=self.format, headers=headers)


def readpage(url, format=None, **kwargs):
    resp = requests.get(url, **kwargs)
    if resp.encoding == resp.apparent_encoding:
        content = resp.text
    else:
        content = resp.content.decode(resp.apparent_encoding)

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
            return BeautifulSoup(resp.content, features="xml")
        case "html":
            return BeautifulSoup(content, features="lxml")
        case _:
            return content
