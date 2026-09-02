#!/usr/bin/env python3
"""Fetch ALL users from the SARC API and build a name -> @mila.quebec email map.

The SARC user endpoint (`/v0/user/query`) is admin-only, so this needs an admin
token exported as SARC_TOKEN (see the mila-sarc skill).
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import replace

from ..config import config
from ..model.classes import Author, Paper
from ..operations import operation, paper_map
from ..utils import AuthError, normalize_name

BASE = "https://sarc.mila.quebec"
MAP = None


def get(path, **params):
    """GET a /v0 endpoint and return the decoded JSON."""
    try:
        token = config.api_keys["sarc"]
    except KeyError:
        raise AuthError(
            "config.api_keys['sarc'] is not set. Open https://sarc.mila.quebec/token in a "
            "browser, sign in with your Mila Google account, copy the "
            "'refresh_token' value, and place it in the config."
        )
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        sys.exit(f"HTTP {e.code} from {path}: {detail}")


def paginate(path, **params):
    """Yield every record from a cursor-paginated /v0 endpoint."""
    cursor = None
    while True:
        q = {**params, "limit": 100}
        if cursor is not None:
            q["cursor"] = cursor
        page = get(path, **q)
        yield from page["results"]
        cursor = page["cursor"]
        if cursor is False:  # note: False, not None — 0/"" are valid cursors
            return


def fetch_all_users():
    """Return the full list of SARC user records."""
    return list(paginate("/v0/user/query"))


def name_map():
    users = fetch_all_users()
    mapping = {}
    for u in users:
        name = u.get("display_name")
        email = u.get("email")
        if not name or not email:
            continue
        if not email.endswith("@mila.quebec"):
            continue
        mapping[normalize_name(name)] = email
    return mapping


@paper_map.variant
def _associate_email(author: Author):
    global MAP

    if author.email is not None:
        return author

    if MAP is None:
        MAP = name_map()

    name = normalize_name(author.name)
    if name in MAP:
        return replace(author, email=MAP[name])
    else:
        return author


@operation
def associate_email(p: Paper):
    return _associate_email(p)
