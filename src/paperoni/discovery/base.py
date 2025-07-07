from dataclasses import dataclass


@dataclass
class Discoverer:
    pass


class QueryError(Exception):
    pass
