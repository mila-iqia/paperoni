from dataclasses import dataclass

from serieux.features.encrypt import Secret
from serieux.features.filebacked import FileBacked


@dataclass
class OpenReviewConfig:
    username: Secret[str] = None
    password: Secret[str] = None
    api_key: Secret[str] = None
    api_key_file: FileBacked[Secret[str]] = None

    def __post_init__(self):
        if not self.api_key:
            self.api_key = self.api_key_file.value or None
