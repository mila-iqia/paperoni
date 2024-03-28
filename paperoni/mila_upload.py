import json
from dataclasses import dataclass, field
from datetime import date
from traceback import print_exc

import gifnoc
import requests
from coleo import Option
from gifnoc import Command, Option as GOption
from requests.auth import HTTPBasicAuth

from paperoni.cli_helper import search
from paperoni.export import export


@dataclass
class Search:
    # Part of the paper's title
    title: str = None
    # An author of the paper
    author: str = None
    # A type:id associated to the author
    author_link: str = None
    # An author's affiliation
    affiliation: str = None
    # A venue of the paper
    venue: str = None
    # A type:id associated to the venue
    venue_link: str = None
    # A type:id associated to the paper
    link: str = None
    # Search for papers published after this date
    start: date = None
    # Search for papers published prior to this date
    end: date = None
    # Search for papers published in that year
    year: int = 0
    # Search for papers with this topic
    topic: str = None
    # Match part of the paper's full text
    excerpt: str = None
    # Field by which to sort the results
    sort: str = None
    # Search for papers with this flag
    flags: list[str] = field(default_factory=list)
    # Allow downloading papers (only if searching by excerpt)
    allow_download: bool = True


@dataclass
class UploadOptions:
    # URL to upload to
    url: str = None
    # User for basic authentication
    user: str = None
    # Password for basic authentication
    password: str = None
    # Token to use for the export
    token: str = None
    # Whether to verify the SSL certificate
    verify_certificate: bool = True
    # Whether to force validation of the papers
    force_validation: bool = False
    # Only dump the paper data
    only_dump: bool = False

    def auth(self):
        return self.user and HTTPBasicAuth(
            username=self.user, password=self.password
        )


search_params = gifnoc.define(
    field="paperoni.cli.search",
    model=Search,
)


upload_options = gifnoc.define(
    field="paperoni.upload_options",
    model=UploadOptions,
)


def export_all(papers):
    results = []
    for p in papers:
        try:
            results.append(export(p))
        except Exception as exc:
            print_exc()
    return results


def misc():
    # [positional: **]
    rest: Option = []

    assert rest[0] == "upload"
    rest = rest[1:]

    with gifnoc.cli(
        options=Command(
            mount="paperoni.cli.search",
            auto=True,
            options={".year": GOption(aliases=["-y"])},
        ),
        argv=rest,
    ):
        if not upload_options.url and not upload_options.only_dump:
            exit("No URL to upload to.")

        papers = search(**vars(search_params._obj()))
        exported = export_all(papers)
        if upload_options.force_validation:
            for p in exported:
                p["flags"].append({"name": "validation", "value": 1})
                p["validated"] = True
        if upload_options.only_dump:
            serialized = json.dumps(exported, indent=4)
            print(serialized)
        else:
            print(len(exported), "papers will be uploaded.")
            response = requests.post(
                url=upload_options.url,
                json=exported,
                auth=upload_options.auth(),
                headers={
                    "X-API-Token": upload_options.token,
                },
                verify=upload_options.verify_certificate,
            )
            print("Response code:", response.status_code)
            print("Response JSON:", response.json())
