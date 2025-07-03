from dataclasses import dataclass
from datetime import datetime

from ..model.classes import Paper


@dataclass
class Discoverer:
    pass


class QueryError(Exception):
    pass


@dataclass(kw_only=True)
class PaperInfo:
    paper: Paper
    key: str
    update_key: str = None
    acquired: datetime
