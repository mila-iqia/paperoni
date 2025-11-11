import webbrowser

from ..display import T
from ..get import RequestsFetcher


def login(endpoint: str, headless: bool = False) -> str:
    """Retrieve an access token from the paperoni server."""
    fetcher = RequestsFetcher()

    if headless:
        response = fetcher.read(
            f"{endpoint}/auth/login?headless=true", format="json", cache_into=None
        )
        print(
            T.bold("Open the following URL in the browser:"),
            T.underline(f"{response['login_url']}"),
            sep="\n",
        )

    else:
        response = fetcher.read(f"{endpoint}/auth/login", format="json", cache_into=None)
        # Open the URL in the browser
        if not webbrowser.open(response["login_url"]):
            # Retry with headless mode
            return login(endpoint, True)

    # Wait for the user to login then get the access token
    response = fetcher.read(
        response["token_url"], format="json", cache_into=None, timeout=600
    )
    return response["access_token"]
