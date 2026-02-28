from dataclasses import dataclass
from pathlib import Path

import gifnoc
from serieux.features.encrypt import Secret


@dataclass
class OpenReviewConfig:
    cache_path: Path = None
    username: Secret[str] = None
    password: Secret[str] = None
    api_key: Secret[str] = None


openreview_config: OpenReviewConfig = gifnoc.define(
    "paperoni.discovery.openreview", OpenReviewConfig
)
