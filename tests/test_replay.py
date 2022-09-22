import coleo

from paperoni.cli import replay


def test_replay(transient_config):
    with coleo.setvars(before="90"):
        replay()
