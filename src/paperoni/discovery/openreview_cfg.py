from dataclasses import dataclass

import gifnoc
from serieux.features.encrypt import Secret


@dataclass
class OpenReviewConfig:
    username: Secret[str] = None
    password: Secret[str] = None
    api_key: Secret[str] = None


openreview_config: OpenReviewConfig = gifnoc.define(
    "paperoni.discovery.openreview", OpenReviewConfig
)
