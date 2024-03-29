import json
import os
from hashlib import md5

from coleo import Option, auto_cli

from paperoni.config import load_config
from paperoni.display import display
from paperoni.model import Institution, Role, UniqueAuthor
from paperoni.utils import tag_uuid


def convert(filename):
    with open(filename) as f:
        data = json.load(f)

    for _, author in data.items():
        match author:
            case {"properties": {"bio": b} as props}:
                props["bio"] = [x for x in b.split("/") if x][-1]
                del props["bio-fr"]

        aname = author["name"]
        yield UniqueAuthor(
            author_id=tag_uuid(md5(aname.encode("utf8")).digest(), "canonical"),
            name=aname,
            aliases=[],
            affiliations=[],
            roles=[
                Role(
                    institution=Institution(
                        category="academia",
                        name="Mila",
                        aliases=[],
                    ),
                    role=role["status"],
                    start_date=(d := role["begin"]) and f"{d} 00:00",
                    end_date=(d := role["end"]) and f"{d} 00:00",
                )
                for role in author["roles"]
            ],
            links=[
                *[
                    {"type": k, "link": v}
                    for k, v in author["properties"].items()
                ],
                *[{"type": "mag", "link": id} for id in author["ids"]],
            ],
            quality=(1.0,),
        )


def show():
    # [positional]
    filename: Option

    for entry in convert(filename):
        print("=" * 80)
        display(entry)


def store():
    # [positional]
    filename: Option

    with load_config(
        os.environ["PAPERONI_CONFIG"], tag="researchers"
    ) as config:
        with config.database as db:
            db.import_all(convert(filename))


if __name__ == "__main__":
    auto_cli(
        {
            "show": show,
            "store": store,
        }
    )
