
Welcome to Paperoni! This is an internal tool for paper management at Mila. Its purpose is to populate the website with an accurate picture of Mila publications, as well as help produce reports to stakeholders and partners.

# Search {: #search}

The search interface allows searching through Paperoni's database of papers. It will search as you type. Results are sorted so that the most recent publications appear on top.

* **Title**: Search by paper title.
* **Author**: Search by author. It is currently not possible to search for multiple authors, nor by author affiliation. We will likely add this functionality in the future.
* **Venue**: Search by venue. Venue aliases are not properly taken into account yet, which means that you may need to search for "Neural Information Processing Systems" instead of "NeurIPS" or vice versa.
* **Excerpt**: Search for strings in the paper's full text.
  * This only works for papers for which we were able to automatically find and download the PDF. Paywalled papers will not appear in such searches, even though they may contain the substring.
  * This option is more compute intensive, so use it sparingly.
* **Start/end date**: Search for a paper that had any release between the start and end date. For example, an article with a preprint in 2022 and a publication in 2023 will appear both in 2022 and in 2023.
* **Validated/Invalidated/Not processed/All**: Only select papers that were manually validated as Mila papers/invalidated, meaning that they are *not* papers from Mila members/not yet validated or invalidated/all papers regardless of validation.

The search result count is displayed below the search interface. It will stream at most 100 papers per second and will cap out at 1000 results because the web browser may become unstable with more results. The symbol "~" next to the count means that there are more results, but the interface will not stream them. You can add `?limit=1000000` in the URL bar and press Enter to change that limit, but that is at your own risk.

## Saving/sharing a search

Click on the **Copy Link** button to put a link in the clipboard. When pasted in the URL bar of your browser, that link will take you to your current search, so that you can easily execute it again at a later date or share it with someone else.

## Exporting search results

Search results can be downloaded as JSON or CSV files. Simply click on the "JSON" or "CSV" button. CSV files can be [imported in Google Sheets](https://blog.golayer.io/google-sheets/import-csv-to-google-sheets) or in Excel.

The 1000 paper limit of the interface does not apply to the export, so you will get all results.

# Validation {: #validation}

The validation interface allows the classification of papers that are considered
to be Mila papers.

Each paper in the interface has a numeric score in the top left and is color-coded accordingly to how likely the system thinks it is a Mila paper:

* **Green**: Quite confident
* **Blue**: Pretty confident
* **Orange**: Probably
* **Red**: Verify

The score is a heuristic that sums up a number for each author where an author scores 10 if they explicitly listed "Mila" as their affiliation, 2 if they are listed as a professor in the database, 1 if they have a page on the Mila website or if they are known to have many homonyms.

## Validation process

For each paper, you must decide whether it is a Mila paper or not. Entries are not deleted from the database, so errors can easily be corrected. To help you, many links are listed at the bottom of the entry. Links ending in `.pdf` will open a new tab with the paper's full text, which is the most valuable. If the article is paywalled, the `doi.abstract` link will take you to the publisher's page for the paper, which usually has all the information you need.

**Select Yes** if:

* The entry is a paper or book, as opposed to a foreword, course description, powerpoint presentation or class notes
    * It does not need to be published in a peer-reviewed venue. Preprints are OK, workshop papers are OK, and so are articles that have been rejected. They may be published at a later date.
* **AND** At least one author wrote "Mila" as their affiliation in the paper (either as printed in the PDF, or listed on the publisher's page -- Paperoni's own information should be reliable most of the time, but there can be mistakes)
* **OR** At least one author worked on the paper while they were affiliated to Mila and wrote their Mila-affiliated institution (Université de Montréal, McGill, etc.)

**Select No** if:

* The entry is not actually a paper
* **OR** No reliable information can be found about the paper
* **OR** No author on the paper has ever been affiliated to Mila.
    * Notably, this can happen if one of the authors is a homonym of a Mila member. Such papers typically have a score of 1 or 2.
* **OR** No author on the paper worked on the paper while they were affiliated to Mila. For example, if a Mila member published papers while they were at Cambridge University, these papers are a **No** unless they involved other Mila members at the time.

**Select Unknown** if:

* You are uncertain about any of the above factors. The paper may be classified at a later date.

# Admin

## Permissions {: #permissions}

Permissions are defined as JSON. Each key must be a path or subpath of the application. The value associated must be a list of emails that have access to that path. An email may contain the character "*" as a wildcard, for example `*@mila.quebec` matches every user that has a `mila.quebec` email.

Notes:

* `/**` is permissions to **everything**.
* A user must have access to the `/report` route to use the CSV or JSON buttons on the search or validation interfaces.
* Consequently, a user who needs search access should have their email in both `/search` *and* `/report`.


## Config {: #config}

The configuration is defined as YAML. The `version_tag` field represents the tag on the Paperoni GitHub repository to use for this app. To update the software, you can change this value and then restart the server by going on [/admin/restart](/admin/restart).

## Restart {: #restart}

When the server restarts, it checks out the version of the code represented by the `version_tag` key in `config.yaml`.

# Troubleshooting

### The page is completely blank

It is likely you pressed the back button on the browser, or came back to the tab after a long time. Try refreshing the page.
