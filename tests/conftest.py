import os
from pathlib import Path

os.environ["GIFNOC_FILE"] = os.environ.get(
    "GIFNOC_FILE", str(Path(__file__).resolve().parent.parent / "config/basic.yaml")
)
