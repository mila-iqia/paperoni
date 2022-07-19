import json

from coleo import Option, auto_cli

from paperoni.config import config, configure
from paperoni.sources.model import Author, Institution, Role
from paperoni.utils import display


def convert(filename):
    with open(filename) as f:
        data = json.load(f)

    for _, author in data.items():
        match author:
            case {"properties": {"bio": b} as props}:
                props["bio"] = b.split("/")[-1]
                del props["bio-fr"]

        yield Author(
            name=author["name"],
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
        )


def show():
    # [positional]
    filename: Option

    for entry in convert(filename):
        print("=" * 80)
        display(entry)


def store():
    from paperoni.db.database import Database

    # [positional]
    filename: Option

    configure("config.yaml", tag="researchers")
    db = Database(config.database_file)
    db.import_all(convert(filename))


if __name__ == "__main__":
    auto_cli(
        {
            "show": show,
            "store": store,
        }
    )
