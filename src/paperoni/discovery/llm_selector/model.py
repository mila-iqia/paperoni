from dataclasses import dataclass
from pathlib import Path

import gifnoc

from ...prompt import PromptConfig
from ...prompt_utils import Explained


@dataclass
class Analysis:
    # CSS selector to iterate all paper entries from the HTML page
    # This selector should target the container element(s) that represent individual papers
    paper_selector: Explained[str]

    # Optional RegEx pattern to help iterate papers if CSS selector alone is not sufficient
    # Leave empty if CSS selector is sufficient. Use this if papers need additional filtering
    # or splitting (e.g., when all papers are in one container and need to be split by a pattern)
    paper_iteration_regex: Explained[str]

    # RegEx pattern to extract relevant links from a single paper entry's HTML/text
    # This should match URLs for PDFs, arXiv, DOI, project websites, publisher pages, etc.
    # The RegEx will be applied to the HTML/text content of each paper entry
    link_extraction_regex: Explained[str]


DEFAULT_SYSTEM_MESSAGE = (Path(__file__).parent / "system-prompt.md").read_text()
FIRST_MESSAGE = """### HTML page to analyze:

{}"""

llm_config: PromptConfig = gifnoc.define(
    "paperoni.llm_selector",
    PromptConfig,
    defaults={"system_prompt_template": DEFAULT_SYSTEM_MESSAGE},
)
