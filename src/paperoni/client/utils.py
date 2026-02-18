import webbrowser

from ..display import T
from ..get import RequestsFetcher


async def login(endpoint: str, headless: bool = False) -> str:
    """Retrieve an access token from the paperoni server."""
    fetcher = RequestsFetcher()

    response = await fetcher.read(
        f"{endpoint}/token?headless=true", format="json", cache_into=None
    )

    if headless or not webbrowser.open(response["login_url"]):
        print(
            T.bold("Open the following URL in the browser:"),
            T.underline(f"{response['login_url']}"),
            sep="\n",
        )

    # Wait for the user to login then get the access token
    response = await fetcher.read(
        response["token_url"], format="json", cache_into=None, timeout=600
    )
    return response["refresh_token"]
