
Welcome to Paperoni! Paperoni is a tool for paper management developed at Mila.

## Table of contents

1. **[Searching for papers](#search)**
1. **[Adding papers](#new)**
1. **[Editing papers](#edit)**

Also see the [validator interface help](/help/validation) and [admin interface help](/help/admin)

## Searching for papers {: #search}

The [Search](/search) interface allows searching through Paperoni's database of
papers. It searches as you type (with a short debounce). Results are sorted so
that the most recent publications appear on top.

* **Title**: Search by paper title.
* **Author**: Search by author name or email (at most one author may be specified).
* **Institution**: Search by author affiliation or institution.
* **Venue**: Search by venue. We try our best to normalize venue names, but sometimes the same venue may be listed under more than one spelling.
* **Topic**: Search by topic. These may be not fully consistent or complete over the whole collection.
* **Start/end date**: Search for a paper that had any release between the start
  and end date. For example, an article with a preprint in 2022 and a
  publication in 2023 will appear both in 2022 and in 2023.
* **Type**: Filter peer-reviewed, preprint, or workshop papers.
* **Peer-reviewed**: Check this box to only show peer-reviewed publications.

By default, Paperoni performs a substring search. You may prefix a search with "=" to perform an exact search.

### Click-to-filter

In the search results, you can click on an author name, institution, venue, or
year to instantly filter results by that value.

### Edit button

An edit icon (<img src="/assets/pen.svg" alt="edit" style="height:1em; vertical-align:middle">) appears next to each paper title. Clicking it opens the [edit page](#edit) for that paper in a new tab, where you can suggest modifications to its title, authors, venues, and other fields.


## Adding papers {: #new}

[The paper addition interface](/edit/new) lets you suggest new papers. Unless you have the *validator* role, these suggestions will not appear immediately in the database, but will rather go to a pending queue for approval. It may take a few days for the paper to appear.

**Before suggesting a paper,** please check whether it is already in the database using the [search](/search) interface.

### Populate

At the top of the interface, you will see a Populate section where you can paste a link to the paper (you may paste several, comma-separated). Paperoni will read the metadata and populate the form for you. Allowed links are:

* **[arxiv](https://arxiv.org)**: e.g. `https://arxiv.org/abs/1810.11530` or `arxiv:1810.11530`
* **DOI**: e.g. `doi:10.1109/comst.2024.3450292`
* **[Semantic Scholar](https://www.semanticscholar.org/)**: e.g. `https://www.semanticscholar.org/paper/9f1ce3ff55eb559e00df33fa40ee6ecd6a2a54f1` or `semantic_scholar:9f1ce3ff55eb559e00df33fa40ee6ecd6a2a54f1`

This only fills the form, it does not submit anything. You may review what was filled in, fix mistakes, add missing venues, and so on.

### Submitting

Once you are done, simply click on the `Suggest Paper` button, bottom right. This will place the paper in a queue for review, so it is normal that you don't see it for a bit when searching for papers right after suggesting it.


## Editing papers {: #edit}

The edit interface lets you suggest changes to all data associated to a paper, including
title, abstract, authors and affiliations, releases (venues and dates), topics,
links, and flags. You can also create a new paper from scratch at
[/edit/new](/edit/new), or delete a paper.

From the search page, click the edit icon (<img src="/assets/pen.svg" alt="edit" style="height:1em; vertical-align:middle">) next to a paper's title to open its edit page.


## API {: #api-token}

Paperoni has an API that you may use to get data programmatically. To use it, you need a bearer token.

1. **Get a token**: Navigate to [Token](/token). Sign in with Google when
   prompted. When the flow finishes, the page will show your token — copy it and
   store it securely.

2. **Use the token**: Send it in the `Authorization` header as
   `Bearer YOUR_TOKEN`.

Example — search (first 10 results):

```
curl -H 'Authorization: Bearer YOUR_TOKEN' \
  'https://paperoni.mila.quebec/api/v1/search?limit=10&offset=0'
```

Replace `YOUR_TOKEN` with the token you copied and adjust the base URL if you
use a different Paperoni instance.

For full REST API reference (endpoints, parameters, schemas), see the [API
documentation](/docs).
