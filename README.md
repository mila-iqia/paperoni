
# Paperoni

Paperoni is Mila's tool to collect publications from our researchers and generate HTML or reports from them.


## Install

First clone the repo, then:

```bash
pip install -e .
```

## Configuration

Create a YAML configuration file named `config.yaml` in the directory where you want to put the data with the following content:

```yaml
paperoni:
  paths:
    database: papers.db
    history: history
    cache: cache
    requests_cache: requests-cache
    permanent_requests_cache: permanent-requests-cache
  institution_patterns:
    - pattern: ".*\\buniversit(y|é)\\b.*"
      category: "academia"
```

All paths are relative to the configuration file. Insitution patterns are regular expressions used to recognize affiliations when parsing PDFs (along with other heuristics).

Make sure to set the `$GIFNOC_FILE` environment variable to the path to that file.


## Start the web app

To start the web app on port 8888, execute the following command:

```bash
starbear serve -m paperoni.webapp --port 8888
```

You can also add this section to the configuration file (same file as the paperoni config):

```yaml
starbear:
  server:
    module: paperoni.webapp
    port: 8888
    dev: true
```

And then you would just need to run `starbear serve` or `starbear serve --config config-file.yaml`.

Once papers are in the system, the app can be used to validate them or perform searches. There are some steps to follow in order to populate the database:


## Add researchers

* Go to [http://127.0.0.1:8888/author-institution](http://127.0.0.1:8888/author-institution)
* Enter a researcher's name, role at the institution, as well as a start date. The end date can be left blank, and then click `Add/Edit`
* You can edit a row by clicking on it, changing e.g. the end date and clicking `Add/Edit`
* Then, add IDs on Semantic Scholar: click on the number in the `Semantic Scholar IDs` column, which will open a new window.
* This will query Semantic Scholar with the researcher's name. Each box represents a different Semantic Scholar ID. Select:
  * `Yes` if the listed papers are indeed from the researcher. This ID will be scraped for this researcher.
  * `No` if the listed papers are not from the researcher. This ID will not be scraped.

Ignore OpenReview IDs for the time being, they might not work properly at the moment.


## Scrape

The scraping currently needs to be done on the command line.

```bash
# Scrape from semantic_scholar
paperoni acquire semantic_scholar

# Get more information for the scraped papers
# E.g. download from arxiv and analyze author list to find affiliations
# It can be wise to use --limit to avoid hitting rate limits
paperoni acquire refine --limit 500

# Merge entries for the same paper; paperoni acquire does not do it automatically
paperoni merge paper_link

# Merge entries based on paper name
paperoni merge paper_name
```

Other merging functions are `author_link` and `author_name` for authors (not papers) and `venue_link` for venues.


## Validate

Go to [http://127.0.0.1:8888/validation](http://127.0.0.1:8888/validation) to validate papers. Basically, you click "Yes" if the paper should be in the collection and "No" if it should not be according to your criteria (because it comes from a homonym of the researcher, is in the wrong field, is just not a paper, etc. -- it depends on your use case.)
