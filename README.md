# Paperoni

Paperoni is Mila's tool to collect publications from researchers and generate
HTML or reports from them. It provides a CLI for discovering, refining, and
managing papers, plus a web interface for searching, validating, and editing.

## Install

Clone the repo, then:

```bash
pip install -e .
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv pip install -e .
```

## Configuration

Create a YAML configuration file and set the `$GIFNOC_FILE` environment variable
to its path. All paths in the config are relative to the config file's
directory.

### Minimal configuration

```yaml
paperoni:
  cache_path: cache
  data_path: data
  collection:
    $class: paperoni.collection.filecoll:FileCollection
    file: ${paperoni.data_path}/collection.json
  work_file: ${paperoni.data_path}/work.json
  focuses: focuses.yaml
  server:
    host: localhost
    port: 8000
```

### Discovery sources

Paperoni discovers papers from multiple sources, configured under
`paperoni.discovery.<source>`:

| Source            | Description                          |
|-------------------|--------------------------------------|
| `semantic_scholar`| Semantic Scholar API                 |
| `openalex`        | OpenAlex API                         |
| `openreview`      | OpenReview                           |
| `miniconf`        | MiniConf (conference proceedings)    |
| `pmlr`            | Proceedings of Machine Learning Research |
| `jmlr`            | Journal of Machine Learning Research |
| `scrape`          | Custom URL scraping (set `urls` in config) |

Example for scraping custom publication pages:

```yaml
paperoni:
  discovery:
    scrape:
      urls:
        - https://example.org/publications
```

### Focuses

Focuses define which authors or institutions to track and how highly to score
them. Create `focuses.yaml`:

```yaml
main:
  - "!institution :: Mila :: 10"
  - "!author :: Yoshua Bengio :: 3"
  - "!author :: Aaron Courville :: 3"
```

Format: `!type :: Name :: score` or `type :: Name :: score`, where `type` is
`author` or `institution`. Omit the leading `!` to only score papers matching
the focus, without discovering papers based on it.

## CLI

### Discover papers

Discover papers from various sources. The discovery source is chosen by the
`command` subcommand:

```bash
# Discover from Semantic Scholar (by author or title)
paperoni discover semantic_scholar --author "Yoshua Bengio"
paperoni discover semantic_scholar --title "Attention is all you need"

# Discover from OpenAlex
paperoni discover openalex --author "Yoshua Bengio"

# Discover from Paperoni v2 (validated papers)
paperoni discover v2

# Limit output and show top N by focus score
paperoni discover semantic_scholar --author "Yoshua Bengio" --top 20
```

Output formats: `--format terminal` (default), `--format json`, `--format yaml`.

### Refine papers

Fetch and enrich paper metadata (DOIs, venues, affiliations, etc.):

```bash
# Refine by link (arxiv:id, semantic_scholar:id, doi:10.1234/..., or URL)
paperoni refine arxiv:2301.12345
paperoni refine https://arxiv.org/abs/2301.12345

# Normalize author, venue, and institution names
paperoni refine arxiv:2301.12345 --norm author venue institution

# Force re-running refinement
paperoni refine arxiv:2301.12345 --force
```

### Fulltext

Locate or download PDFs:

```bash
# Find PDF URLs for a paper
paperoni fulltext locate arxiv:2301.12345

# Download PDF
paperoni fulltext download arxiv:2301.12345
paperoni fulltext download arxiv:2301.12345 --cache-policy force
```

### Work (workset)

Manage a working set of candidate papers before adding them to the collection.

```bash
# Initialize workset for top 100 papers
paperoni work configure -n 100

# Fetch papers from discovery sources (uses focuses from config)
paperoni work get semantic_scholar

# View papers in the workset
paperoni work view paper
paperoni work view title -n 10

# Refine papers in the workset
paperoni work refine -n 50

# Normalize author/venue/institution
paperoni work normalize -n 50

# Add top papers to the collection (above score threshold)
paperoni work include -n 20 --score 10.0

# Exclude low-scoring papers
paperoni work exclude -n 10 --score 1.0

# Clear the workset
paperoni work clear
```

Options: `-w` / `--work-file` for workset file, `-f` / `--focus-file` for
focuses, `-c` / `--collection-file` for collection.

### Collection operations

```bash
# Search the collection
paperoni coll search --author "Bengio" --venue "NeurIPS" --start-date 2020-01-01
paperoni coll search --title "transformer" --format json
paperoni coll search --flags valid  # only validated papers
paperoni coll search --flags ~invalid  # exclude invalidated papers

# Import papers from a file
paperoni coll import papers.json

# Export the collection
paperoni coll export
paperoni coll export papers.json

# Validate papers (from the v2 discoverer or by score threshold)
paperoni coll validate v2
paperoni coll validate --threshold 5.0

# Diff two collections
paperoni coll diff other_collection.json --out ./diff

# Drop the collection (use --force to skip confirmation)
paperoni coll drop --force
```

Options: `-c` / `--collection-path` for collection file or remote URL.

### Serve the web app

```bash
# Start the server (default: localhost:8000)
paperoni serve

# Custom host and port
paperoni serve --host 0.0.0.0 --port 8888

# Development mode with auto-reload
paperoni serve --reload

# Without authentication (not for production)
paperoni serve --no-auth
```

### Batch mode

Run multiple paperoni commands from a YAML or JSON file:

```bash
paperoni batch batch.yaml
```

### Global options

* `--config PATH` — load an additional config overlay
* `--dash` / `--no-dash` — enable or disable the rich terminal dashboard
* `--log` — enable slow operation logging
* `--report` — send execution report to configured reporters
* `--rich-log` — write a JSONL log file for debugging

## Web interface

Start the server with `paperoni serve`, then open the app in your browser.

### Main pages

| Route          | Description                                      | Capability |
|----------------|--------------------------------------------------|------------|
| `/`            | Home page with links to main features            | —          |
| `/search`      | Search papers by title, author, venue, dates     | search     |
| `/validate`    | Validate or invalidate papers interactively      | validate   |
| `/edit/{id}`   | Edit paper metadata                              | validate   |
| `/exclusions`  | Manage excluded papers                           | validate   |
| `/latest-group`| Generate latest papers digest (peer-reviewed, preprints) | validate |
| `/workset`     | Manage the working set of candidate papers       | admin      |
| `/focuses`     | Edit focus rules (authors, institutions)         | admin      |
| `/capabilities`| Manage user capabilities                         | admin      |
| `/report`      | View execution logs from `--rich-log`            | dev        |
| `/help`        | Help and documentation                           | —          |
| `/docs`        | REST API documentation (OpenAPI/Swagger)         | —          |

### Search

* **Title**: Search by paper title
* **Author**: Search by author name
* **Venue**: Search by venue (e.g. NeurIPS, ICML)
* **Start/End date**: Filter by publication date
* **Validation**: Filter by validated / invalidated / not processed / all

Results can be exported as JSON or CSV.

### Validation

Classify papers as valid or invalid for your collection. Use "Yes" for papers
that belong and "No" for those that do not (wrong author, wrong field, etc.).

### Authentication

The web app uses OAuth (e.g. Google). Configure `paperoni.server.auth` in your
config. Capabilities (search, validate, admin, dev) control access to each
feature and are managed via the capabilities page or `user_overrides` in config.

For OAuth setup details, see the
[easy-oauth documentation](https://github.com/mila-iqia/easy-oauth?tab=readme-ov-file#reading-configuration-from-a-file).

## Typical workflow

1. **Configure** — Create `config.yaml` and `focuses.yaml` with your authors and
   institutions.
2. **Workset** (optional) — Use `paperoni work configure`, `paperoni work get`,
   `paperoni work refine`, then `paperoni work include` to curate candidates
   before adding to the collection.
3. **Add to collection** — Either via `paperoni work include` or `paperoni coll import`.
4. **Validate** — Use the web interface at `/validate` to mark papers as valid
   or invalid.
5. **Search & export** — Use `/search` to find papers and export as JSON or CSV.
