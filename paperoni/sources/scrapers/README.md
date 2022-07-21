
# Defining a new scraper

To define a new scraper called `scraperoni`, create a `scraperoni.py` file in this directory with the following contents:

```python
from coleo import tooled, Option

class ScraperoniScraper:
    @tooled
    def query(
        self,
        # Define option documentation as a comment on the previous line
        # [alias: -o]
        option: Option,
        # Use & bool for boolean flags
        flag: Option & bool,
    ):
        # mpap query scraperoni --option xyz --flag
        print(f"{option=}")
        print(f"{flag=}")

    @tooled
    def prepare(self, queries):
        # mpap prepare scraperoni
        return []

    @tooled
    def acquire(self, queries):
        # mpap acquire scraperoni
        return []


# Define __scrapers__ so that the scraper can be found
__scrapers__ = {"scraperoni": ScraperoniScraper()}
```

You may define three methods: `query`, `prepare` and `acquire`.

## query

`query` is meant to simply query the scraper. This is the first method that should be defined, and it should be used to test that the right papers with the right information are produced. `query` must return or yield a list of `paperoni.sources.model.Paper`. Try to implement it as a generator if possible.

You may add any options you want, depending on what the scraper supports. For example, you may have `--author` if it can query by author, or `--conference` if it can query by conference name, or no options if it cannot be configured.

The options should be defined using [coleo](https://github.com/breuleux/coleo#coleo). Most options should be defined as arguments, so that the `query` method can be called programmatically outside of `coleo`.

## prepare

`prepare` is only relevant for certain scrapers that associate researchers to IDs (for example, Semantic Scholar or OpenAlex).

As input it takes a list of `paperoni.sources.model.AuthorQuery` (you can ignore the `author_id` field). It should return or yield a list of `paperoni.sources.model.AuthorQuery` that will add extra information to the given authors.

For example, if `auq` is the first `AuthorQuery`, and `auq.author.name == "Olivier Breuleux"`, you could yield:

```python
yield AuthorQuery(
    author_id=auq.author_id,
    author=Author(
        name="Olivier Breuleux",
        aliases=["O Biggie"],
        links=[Link(type="scraperoni", "link"="123456789")],
        ...
    )
)
```

The `Link` instance would be saying that the `scraperoni` ID for Olivier is `123456789`, so that we can query his papers using that ID. Aliases are other names the author is known by.

If the scraper does not keep such IDs, or if we are not going to query by author, then this method should return an empty list.

## acquire

`acquire` takes a list of `paperoni.source.model.AuthorPaperQuery` and should return or yield a list of `paperoni.source.model.Paper` that will be added to the database.

* An `AuthorPaperQuery` contains an `author`. If the scraper cannot query by author, ignore the entire list of `AuthorPaperQuery`.
* An `AuthorPaperQuery` contains a `start_date` and an `end_date`. If it is possible for the scraper to filter by date, they should be used, otherwise simply ignore them.
