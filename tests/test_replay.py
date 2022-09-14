import os
from pathlib import Path

import coleo

from paperoni.cli import replay
from paperoni.config import load_config


def test_replay():
    os.environ["PAPERONI_CONFIG"] = str(
        Path(__file__).parent / "data" / "transient-config.yaml"
    )
    cfg = load_config()
    dbf = Path(cfg.database_file)
    if dbf.exists():
        dbf.unlink()
    with coleo.setvars(before="90"):
        replay()
