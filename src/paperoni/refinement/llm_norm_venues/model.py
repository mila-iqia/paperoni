from dataclasses import dataclass
from pathlib import Path

import gifnoc

from ..llm_common import Explained, PromptConfig


@dataclass
class Analysis:
    # The normalized full official venue name
    name: Explained[str]
    # The normalized widely used short or abbreviated name
    short_name: Explained[str]
    # The extracted numeric marker
    numeric_marker: Explained[str]
    # The extracted year
    year: Explained[str]


DEFAULT_SYSTEM_MESSAGE = (Path(__file__).parent / "system-prompt.md").read_text()
FIRST_MESSAGE = """### The academic venue name to normalize:
{}"""

llm_config: PromptConfig = gifnoc.define(
    "paperoni.llm_norm_venues",
    PromptConfig,
    defaults={"system_prompt_template": DEFAULT_SYSTEM_MESSAGE},
)
