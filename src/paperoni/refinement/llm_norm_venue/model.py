from dataclasses import dataclass
from pathlib import Path

import gifnoc

from ...prompt import PromptConfig
from ...prompt_utils import Explained


@dataclass
class Analysis:
    # Full standardized name of the parent venue (conference, journal). For workshops, this is the parent conference/journal, not the workshop title.
    name: Explained[str]
    # Common abbreviation of the parent venue (e.g., "ICML", "CVPR"). For workshops, the conference acronym, not the workshop acronym.
    short_name: Explained[str]
    # Specific workshop name or acronym when the venue is a workshop (e.g., "CODEML"). Empty for main conferences, journals, or non-workshop venues.
    workshop_name: Explained[str]
    # Edition, volume, or index number (never the year).
    numeric_marker: Explained[str]
    # Year when explicitly stated (e.g., "2025").
    year: Explained[str]


DEFAULT_SYSTEM_MESSAGE = (Path(__file__).parent / "system-prompt.md").read_text()
FIRST_MESSAGE = """### The academic venue name to normalize:
{}"""

llm_config: PromptConfig = gifnoc.define(
    "paperoni.llm_norm_venues",
    PromptConfig,
    defaults={"system_prompt_template": DEFAULT_SYSTEM_MESSAGE},
)
