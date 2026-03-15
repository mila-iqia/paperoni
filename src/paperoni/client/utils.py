import webbrowser

from ..display import T


def login(endpoint: str) -> str:
    """Retrieve an access token from the paperoni server."""
    print(
        T.bold("Open the following URL in the browser:"),
        T.underline(f"{endpoint}/token"),
        sep="\n",
    )
    webbrowser.open(f"{endpoint}/token")
