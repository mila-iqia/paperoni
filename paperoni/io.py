import json

from .papers import Papers
from .researchers import Researchers


def ResearchersFile(filename):
    """Parse a file containing researchers."""
    try:
        with open(filename, "r") as file:
            data = json.load(file)
    except FileNotFoundError:
        data = {}
    return Researchers(data, filename=filename)


def PapersFile(filename):
    """Parse a file containing papers."""
    with open(filename, "r") as file:
        data = json.load(file)
    return Papers(data, filename=filename)
