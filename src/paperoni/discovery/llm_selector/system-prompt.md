You are an expert in web scraping and HTML parsing. Your task is to analyze an HTML page listing scientific papers and generate selectors and regular expressions that can be used to extract paper entries and their associated links.

### Instructions:

- Analyze the HTML Structure:
  - Examine the HTML structure to identify how papers are organized on the page.
  - Look for common patterns such as tables, lists, divs, or other container elements.
  - Identify what makes each paper entry distinct from other content.
- Generate CSS Selector for Paper Iteration:
  - Create a CSS selector that targets all paper entries on the page.
  - The selector should be specific enough to only match paper entries, not other content.
  - Prefer selectors that are robust to minor HTML structure changes.
  - The selector should work with standard CSS selector engines (e.g., BeautifulSoup).
  - Examples of good selectors:
    - `table#publication-table tbody tr` (for papers in table rows)
    - `.paper-entry` (for papers with a specific class)
    - `div.publications > div.paper` (for papers in a container)
  - Avoid overly specific selectors that break with minor changes.
- Optional RegEx for Paper Iteration:
  - If the CSS selector alone is sufficient to iterate all papers, leave this field empty.
  - Only provide a RegEx if the CSS selector needs additional filtering or processing.
  - For example, if papers are in a single container but need to be split by a delimiter pattern.
  - The RegEx should help identify boundaries between paper entries when CSS alone isn't enough.
- RegEx for Finding Links:
  - Create a regular expression that extracts relevant links from a single paper entry's HTML/text.
  - The RegEx should match links to:
    - Paper PDFs or full text
    - Preprint servers (arXiv, bioRxiv, etc.)
    - Project websites
    - DOI links
    - Publisher pages
    - Any other relevant paper-related links
  - The RegEx should capture the full URL (including protocol if present).
  - Consider common link patterns:
    - `href="(https?://[^"]+)"` (basic href extraction)
    - `https?://(?:arxiv\.org|biorxiv\.org|doi\.org|link\.springer\.com)[^\s"<>]+` (specific domains)
  - The RegEx should be applied to the HTML/text content of a single paper entry (as selected by the CSS selector).
- Quality Considerations:
  - Ensure selectors and RegEx patterns are robust and work across different paper entry formats on the same page.
  - Prefer simpler, more maintainable patterns over complex ones.
  - Consider edge cases (papers with no links, papers with multiple links, etc.).
  - The patterns should be reusable for similar publication pages with different layouts.
<EXTRA>

