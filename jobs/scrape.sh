#!/bin/bash

# Acquire and refine papers
paperoni acquire semantic_scholar
paperoni acquire semantic_scholar_author
paperoni acquire openreview
paperoni acquire openreview2
paperoni acquire mlr
paperoni acquire neurips
paperoni acquire jmlr
paperoni acquire refine --limit 500

# Merge duplicates
paperoni merge author_link
paperoni merge paper_link
paperoni merge paper_name
paperoni merge author_link
paperoni merge author_name
