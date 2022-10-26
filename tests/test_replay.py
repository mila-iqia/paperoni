import coleo

from paperoni.cli import replay


def test_replay(config_empty):
    with coleo.setvars(before="90"):
        replay()
