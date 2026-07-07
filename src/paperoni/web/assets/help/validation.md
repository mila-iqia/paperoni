
The endpoints on this page require the *validator* capability.

## Table of contents

1. **[Validating papers](#pending)**
1. **[Focuses](#focuses)**
1. **[Newsletter generation](#latest-group)**


## Validating papers {: #pending}

The [pending papers](/pending) list contains new papers and suggested edits to existing papers, submitted either through the [edit interface](/edit) or through automated scraping.

For each paper, **Approve** or **Reject** the addition or change using the appropriate button, and once you are done, you must confirm the changes using the button at the bottom.

If this is more efficient for you, you may use the up and down arrows to navigate the papers, and the "A" and "R" keys of your keyboard to accept/reject.


## Focuses {: #focuses}

The [Focuses](/focuses) page lets you configure research focuses that drive paper discovery and scoring. There are two tabs:

* **Main**: Core focuses that define the research interests (authors, venues, topics, etc.) and their associated scores.
* **Auto**: Automatically generated focuses. Use the "Autogenerate" button to regenerate them from the current collection.

Each focus has a type, name, score, and an optional flag that controls whether
it drives discovery of new papers.


## Newsletter generation {: #latest-group}

The [Latest Group](/latest-group) page helps discover recently published papers. You can set an anchor date and a window (days back/forward) to find new papers. The anchor date is the center of the search window: Paperoni searches from `anchor date - days back` to `anchor date + days forward` (inclusive). For example, if the anchor date is `2026-02-19`, with `days back = 30` and `days forward = 0`, the interval is `2026-01-20` to `2026-02-19`. If you set `days forward = 7`, the interval becomes `2026-01-20` to `2026-02-26`. Results are split into peer-reviewed publications and preprints.

A newsletter can be generated from these results.
