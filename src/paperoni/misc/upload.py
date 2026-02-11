import asyncio
import json
import time
from dataclasses import dataclass

import gifnoc
import requests
from outsight.ops import buffer, enumerate
from requests.auth import HTTPBasicAuth
from serieux import serialize
from serieux.features.encrypt import Secret

from ..config import config
from ..model.classes import Paper


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

    def auth(self):
        return self.user and HTTPBasicAuth(username=self.user, password=self.password)


upload_options = gifnoc.define(
    field="paperoni.upload_options",
    model=UploadOptions,
)


async def main():
    if not upload_options.url and not upload_options.only_dump:
        exit("No URL to upload to.")

    async for i, block in enumerate(
        buffer(config.collection.search(), count=upload_options.block_size)
    ):

        def _export(paper: Paper):
            ser = serialize(Paper, paper)
            valid = "valid" in paper.flags
            if not paper.releases or paper.releases[0].peer_review_status not in {
                "peer-reviewed",
                "preprint",
                "workshop",
            }:
                valid = False
            ser["validated"] = valid
            return ser

        if i > 0 and upload_options.block_pause:
            time.sleep(upload_options.block_pause)

        exports = [_export(paper) for paper in block]
        if upload_options.only_dump:
            serialized = json.dumps(exports, indent=4)
            print(serialized)

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
