import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone

import gifnoc
import requests
from outsight.ops import buffer, enumerate
from ovld import Medley, call_next
from requests.auth import HTTPBasicAuth
from serieux import Context, Serieux
from serieux.features.encrypt import Secret

from paperoni.utils import expand_links_dict

from ..config import config
from ..model.classes import (
    Author,
    DatePrecision,
    Paper,
    PaperAuthor,
    Release,
    Venue,
    dataclass,
)


@dataclass
class UploadOptions:
    # URL to upload to
    url: str = None
    # User for basic authentication
    user: str = None
    # Password for basic authentication
    password: Secret[str] = None
    # Token to use for the export
    token: Secret[str] = None
    # Whether to verify the SSL certificate
    verify_certificate: bool = True
    # Whether to force validation of the papers
    force_validation: bool = False
    # Only dump the paper data
    only_dump: bool = False
    # Number of papers to upload at a time
    block_size: int = 100
    # Number of seconds to wait between two uploads
    block_pause: float = 10
    # Start date
    start_date: date = None

    def auth(self):
        return self.user and HTTPBasicAuth(username=self.user, password=self.password)


upload_options = gifnoc.define(
    field="paperoni.upload_options",
    model=UploadOptions,
)


class UploadSerieux(Medley):
    def serialize(self, t: type[Paper], obj: Paper, ctx: Context):
        ser = call_next(t, obj, ctx)
        valid = True
        if not obj.releases or obj.releases[0].peer_review_status not in {
            "peer-reviewed",
            "preprint",
            "workshop",
        }:
            valid = False
        ser["releases"] = ser["releases"][:1]
        ser["validated"] = valid
        ser["flags"] = [{"name": "validation", "value": 1}]
        ser["citation_count"] = 0
        ser["excerpt"] = None
        ser["paper_id"] = ser["id"]
        del ser["id"]
        del ser["key"]
        del ser["info"]
        del ser["score"]
        del ser["version"]
        ser["links"] = [lnk for lnk in expand_links_dict(obj.links) if "url" in lnk]
        return ser

    def serialize(self, t: type[Venue], obj: Venue, ctx: Context):
        ser = call_next(t, obj, ctx)
        iso_date = ser["date"]
        timestamp = int(
            datetime.fromisoformat(iso_date).replace(tzinfo=timezone.utc).timestamp()
        )
        ser["date"] = {
            "text": DatePrecision.format(date=obj.date, precision=obj.date_precision),
            "timestamp": timestamp,
            "precision": ser["date_precision"],
        }
        ser["venue_id"] = hashlib.md5(obj.name.encode()).hexdigest()
        del ser["date_precision"]
        del ser["short_name"]
        del ser["aliases"]
        del ser["open"]
        del ser["peer_reviewed"]
        return ser

    def serialize(self, t: type[Release], obj: Release, ctx: Context):
        ser = call_next(t, obj, ctx)
        ser["peer_reviewed"] = ser["peer_review_status"] == "peer-reviewed"
        del ser["peer_review_status"]
        return ser

    def serialize(self, t: type[PaperAuthor], obj: PaperAuthor, ctx: Context):
        ser = call_next(t, obj, ctx)
        ser["author"]["name"] = ser["display_name"]
        del ser["display_name"]
        ser["affiliations"] = []
        return ser

    def serialize(self, t: type[Author], obj: Author, ctx: Context):
        ser = call_next(t, obj, ctx)
        ser["author_id"] = hashlib.md5(obj.name.encode()).hexdigest()
        del ser["aliases"]
        return ser


srx = (Serieux + UploadSerieux)()


async def to_async_list(li):
    for x in li:
        yield x


async def main():
    if not upload_options.url and not upload_options.only_dump:
        exit("No URL to upload to.")

    # Drain all papers, otherwise the cursor may become invalid
    all_papers = [
        paper
        async for paper in config.collection.search(start_date=upload_options.start_date)
    ]
    all_papers = to_async_list(all_papers)

    total = 0
    async for i, block in enumerate(buffer(all_papers, count=upload_options.block_size)):
        total += len(block)
        print(total)

        exports = [srx.serialize(Paper, paper) for paper in block]
        if upload_options.only_dump:
            serialized = json.dumps(exports, indent=4)
            print(serialized)
            break

        else:
            print(len(exports), "papers will be uploaded.")
            response = requests.post(
                url=upload_options.url,
                json=exports,
                auth=upload_options.auth(),
                headers={
                    "X-API-Token": upload_options.token,
                },
                verify=upload_options.verify_certificate,
            )
            print("Response code:", response.status_code)
            print("Response:", response.text)


if __name__ == "__main__":
    asyncio.run(main())
