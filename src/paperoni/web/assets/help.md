
Welcome to Paperoni! Paperoni is a tool for paper management.

# Search {: #search}

The [Search](/search) interface allows searching through Paperoni's database of
papers. It searches as you type (with a short debounce). Results are sorted so
that the most recent publications appear on top.

* **Title**: Search by paper title.
* **Author**: Search by author. It is currently not possible to search for
  multiple authors. We will likely add this functionality in the future.
* **Institution**: Search by author affiliation or institution.
* **Venue**: Search by venue. Venue aliases are not always taken into account,
  so you may need to search for "Neural Information Processing Systems" instead
  of "NeurIPS" or vice versa.
* **Start/end date**: Search for a paper that had any release between the start
  and end date. For example, an article with a preprint in 2022 and a
  publication in 2023 will appear both in 2022 and in 2023.
* **Peer-reviewed**: Check this box to only show peer-reviewed publications.
* **Validated/Invalidated/Not processed/All**: Filter papers by their manual
  validation status.

## Click-to-filter

In the search results, you can click on an author name, institution, venue, or
year to instantly filter results by that value.

## Edit button

If you have validation permissions, an edit icon (<img src="/assets/pen.svg"
alt="edit" style="height:1em; vertical-align:middle">) appears next to each
paper title. Clicking it opens the edit page for that paper in a new tab, where
you can modify its title, authors, venues, and other fields.

# Validation {: #validation}

The [Validation](/validate) interface allows the validation or invalidation of
papers, in order to make the database cleaner. It provides the same search
interface as the search page, with additional buttons on each paper to mark it
as valid or invalid. Paper scores are also displayed to help prioritize
validation.

# Editing papers {: #edit}

The edit interface lets you change all data associated to a paper, including
title, abstract, authors and affiliations, releases (venues and dates), topics,
links, and flags. You can also create a new paper from scratch at
[/edit/new](/edit/new), or delete a paper.

From the search or validation pages, click the edit icon on a paper to open its
edit page.

# Exclusions {: #exclusions}

The [Exclusions](/exclusions) page lets you manage a list of excluded paper
identifiers. Excluded identifiers (e.g. `arxiv:1234.5678`, `doi:10.1234/...`)
will be filtered out during paper discovery. You can add exclusions individually
or in bulk (one per line), and remove them as needed.

# Focuses {: #focuses}

The [Focuses](/focuses) page lets administrators configure research focuses that
drive paper discovery and scoring. There are two tabs:

* **Main**: Core focuses that define the research interests (authors, venues,
  topics, etc.) and their associated scores.
* **Auto**: Automatically generated focuses. Use the "Autogenerate" button to
  regenerate them from the current collection.

Each focus has a type, name, score, and an optional flag that controls whether
it drives discovery of new papers.

# Workset {: #workset}

The [Workset](/workset) page shows papers in the current working set, scored and
ranked by relevance to the configured focuses. Papers are displayed with their
scores and metadata, and PDF links are available when fulltext has been located.

# Latest group {: #latest-group}

The [Latest Group](/latest-group) page helps discover recently published papers.
You can set an anchor date and a window (days back/forward) to find new papers.
The anchor date is the center of the search window: Paperoni searches from
`anchor date - days back` to `anchor date + days forward` (inclusive). For
example, if the anchor date is `2026-02-19`, with `days back = 30` and `days
forward = 0`, the interval is `2026-01-20` to `2026-02-19`. If you set `days
forward = 7`, the interval becomes `2026-01-20` to `2026-02-26`. Results are
split into peer-reviewed publications and preprints. A newsletter can be
generated from these results.

# Capabilities {: #capabilities}

The [Capabilities](/capabilities) page lets administrators manage user accounts
and their permissions. You can add users, and grant or revoke capabilities such
as `search`, `validate`, `admin`, and others. Implicit capabilities (derived
from the capability hierarchy) are shown visually alongside directly assigned
ones.

# Reports {: #reports}

The [Reports](/report) page lists available error reports generated from
processing logs. Each report shows errors grouped by type, with tracebacks and
occurrence counts. This is primarily useful for developers and administrators
debugging data processing issues.
