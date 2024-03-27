#!/bin/bash

# Acquire and refine papers
paperoni acquire semantic_scholar
paperoni acquire openreview
paperoni acquire openreview2
paperoni acquire openreview-venues
paperoni acquire refine --limit 500

# Merge duplicates
paperoni merge paper_link
paperoni merge paper_name
paperoni merge author_link
paperoni merge author_name
paperoni merge venue_link
