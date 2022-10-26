import json
from pathlib import Path
from ovld import ovld, OvldMC


class Artifact(metaclass=OvldMC):
    def __init__(self, data):
        self.data = data

    @ovld
    def same(self, value: str):
        return self.same(json.loads(value))

    @ovld
    def same(self, value: dict):
        return all(value[k] == v for k, v in self.data.items())

    @ovld
    def same(self, value: object):
        return self.same(value.tagged_json())

    def isin(self, entries):
        for e in entries:
            if self.same(e):
                return e
        return None


class Artifacts:
    def __init__(self, stem):
        self.artifacts = json.load(open(Path(__file__).parent / f"{stem}.json"))

    def __getitem__(self, name):
        return Artifact(self.artifacts[name])
