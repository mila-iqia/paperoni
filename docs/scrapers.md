
# Scrapers

This is a list of existing scrapers.


# semantic_scholar

This scraper queries [Semantic Scholar](https://www.semanticscholar.org/) for papers. This is the main way to *find* papers.

**prepare**: Gather IDs for our researchers.

**acquire**: For each of our researchers and each of their IDs, query their papers.


# openreview

Queries [OpenReview](https://openreview.net/). OpenReview is what several important conferences use to perform the peer review process and publish their decisions.


# zeta-alpha (WIP)

Queries [Zeta Alpha](https://www.zeta-alpha.com/). Zeta Alpha specializes in collecting, analyzing and providing recommendation for papers in machine learning.

**acquire**: Search by organization (Mila, University of Montreal, McGill, etc.) to find papers that we may have missed through Semantic Scholar.


# refine

This scraper does not find new papers. Based on papers we have already found, it fetches additional information based on the DOI or other IDs or links.

## crossref

Queries Crossref based on the DOI of a specific paper.

## ieeexplore

Queries IEEExplore's API based on the DOI of a specific paper.

## biorxiv

Queries biorxiv's API based on the DOI of a specific paper.

## pubmedcentral

Queries PMC's API based on the DOI of a specific paper.

## sciencedirect

Parses the redirects and the HTML from ScienceDirect to try and find affiliations.

## pdf

* Downloads the PDF for the paper from arxiv, OpenReview or any other link.
* Converts the PDF to plain text.
* Parses the text, as well as can be, for affiliation data.
