from pathlib import Path


def load_scrapers():
    scrapers = {}
    for file in Path(__file__).parent.iterdir():
        if file.name.endswith(".py") and not file.name.startswith("__"):
            mod = __import__(__spec__.name, fromlist=[file.stem])
            mod = getattr(mod, file.stem)
            scrapers.update(getattr(mod, "__scrapers__", {}))
    return scrapers
