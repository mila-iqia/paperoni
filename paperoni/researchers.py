import json
from dataclasses import dataclass


@dataclass
class Role:
    """Represents a role a researcher has/had for a certain time period."""

    status: str = "unknown"
    begin: str = None
    end: str = None

    def __contains__(self, date):
        b = self.begin or "\x00"
        e = self.end or "\xFF"
        return b <= date <= e


class Researchers:
    """Collection of researchers."""

    def __init__(self, researchers, filename=None):
        self.data = {}
        self.data_by_id = {}
        self.filename = filename
        for author_name, author_data in researchers.items():
            author = Researcher(author_data)
            self.data[author_name] = author
            for aid in author_data["ids"]:
                self.data_by_id[aid] = author

    def __iter__(self):
        return iter(self.data.values())

    def get(self, name):
        key = name.lower()
        if key in self.data:
            return self.data[key]
        else:
            r = Researcher(
                {
                    "name": name,
                    "ids": [],
                    "noids": [],
                    "properties": {},
                    "roles": [],
                }
            )
            self.data[key] = r
            return r

    def find(self, authid):
        if authid in self.data_by_id:
            return self.data_by_id[authid]
        else:
            return Researcher(None)

    def save(self):
        data = {
            auth_name.lower(): auth.data
            for auth_name, auth in self.data.items()
        }
        text = json.dumps(data, indent=4)
        with open(self.filename, "w") as file:
            file.write(text)


class Researcher:
    """Represents a researcher.

    Attributes:
        ids: Set of matching ids in Microsoft Academic's database.
        noids: Set of ids that do *not* correspond to this person.
        properties: Arbitrary properties
        roles: List of roles taken by that researcher.
    """

    def __init__(self, data):
        self.data = data
        if data:
            self.name = self.data["name"]
            self.ids = self.data["ids"]
            self.noids = self.data["noids"]
            self.properties = self.data["properties"]
            self.roles = [Role(**role) for role in self.data["roles"]]
        else:
            self.name = None
            self.ids = []
            self.noids = []
            self.properties = {}
            self.roles = []

    @property
    def listed(self):
        return self.data is not None

    def with_status(self, *statuses):
        """Return roles with one of the statuses.

        If statuses is an empty list, returns all roles. If status is
        empty and there are no roles, return an empty role.
        """
        if not statuses:
            return self.roles or [Role()]
        else:
            return [r for r in self.roles if r.status in statuses]

    def roles_at(self, date):
        """Return roles held by the researcher at the given date."""
        return [role for role in self.roles if date in role]

    def status_at(self, date):
        """Return statuses held by the researcher at the given date."""
        return {role.status for role in self.roles_at(date)}
