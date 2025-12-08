from dataclasses import dataclass
from pathlib import Path

import gifnoc

from ...prompt import PromptConfig
from ...prompt_utils import Explained


@dataclass
class Analysis:
    # The normalized author name
    normalized_author: Explained[str]


DEFAULT_SYSTEM_MESSAGE = (Path(__file__).parent / "system-prompt.md").read_text()
FIRST_MESSAGE = """### The author name to normalize:

{}"""

llm_config: PromptConfig = gifnoc.define(
    "paperoni.llm_norm_author",
    PromptConfig,
    defaults={"system_prompt_template": DEFAULT_SYSTEM_MESSAGE},
)
