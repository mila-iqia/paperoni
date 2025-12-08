from dataclasses import dataclass
from pathlib import Path

import gifnoc

from ...model.classes import InstitutionCategory
from ...prompt import PromptConfig
from ...prompt_utils import Explained


@dataclass
class Affiliation:
    # The normalized academic affiliation name
    name: Explained[str]
    # The institution category
    category: Explained[InstitutionCategory]
    # The country of the institution
    country: Explained[str]


@dataclass
class Analysis:
    # The normalized academic affiliation names with category and country
    affiliations: list[Affiliation]


DEFAULT_SYSTEM_MESSAGE = (Path(__file__).parent / "system-prompt.md").read_text()
FIRST_MESSAGE = """### The academic affiliation names to process:

{}"""


llm_config: PromptConfig = gifnoc.define(
    "paperoni.llm_process_affiliation",
    PromptConfig,
    defaults={"system_prompt_template": DEFAULT_SYSTEM_MESSAGE},
)
