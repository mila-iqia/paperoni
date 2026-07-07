
The endpoints on this page require the *admin* capability.

## Table of contents

1. **[Exclusions](#exclusions)**
1. **[Workset](#workset)**
1. **[Capabilities](#capabilities)**
1. **[Reports](#reports)**


## Exclusions {: #exclusions}

The [Exclusions](/exclusions) page lets you manage a list of excluded paper identifiers. Excluded identifiers (e.g. `arxiv:1234.5678`, `doi:10.1234/...`) will be filtered out during paper discovery. You can add exclusions individually or in bulk (one per line), and remove them as needed.


## Workset {: #workset}

The [Workset](/workset) page shows papers in the current working set, scored and
ranked by relevance to the configured focuses. Papers are displayed with their
scores and metadata, and PDF links are available when fulltext has been located.


## Capabilities {: #capabilities}

The [Capabilities](/capabilities) page lets administrators manage user accounts and their permissions. You can add users, and grant or revoke capabilities such as `search`, `validate`, `admin`, and others. Implicit capabilities (derived from the capability hierarchy) are shown visually alongside directly assigned ones.


## Reports {: #reports}

The [Reports](/report) page lists available error reports generated from processing logs. Each report shows errors grouped by type, with tracebacks and occurrence counts. This is primarily useful for developers and administrators debugging data processing issues.
