import asyncio
import os
import signal

from hrepr import H
from starbear import Queue, bear

from ..common import mila_template


@bear
@mila_template
async def app(page, box):
    """Restart the server."""
    q = Queue()

    box.print(H.button("Restart server", onclick=q))

    async for _ in q:
        box.set("Restarting. Try to refresh in a few seconds.")
        await asyncio.sleep(
            0
        )  # Make sure we send the feedback before the kill()
        try:
            os.kill(os.getpid(), signal.SIGTERM)
        except Exception as exc:
            box.print(H.div["error"]("An error occurred"))
            box.print(H.div["error"](exc))


ROUTES = app
