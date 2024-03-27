import asyncio
import os
import signal

from hrepr import H
from starbear import Queue

from ...config import papconf
from ..common import mila_template


@mila_template(help="/help#operations")
async def app(page, box):
    """Admin operations."""
    q = Queue()

    box.print(H.p(H.button("Restart server", onclick=q.tag("restart"))))
    box.print(H.p(H.a("Download database", href=papconf.paths.database)))

    async for _ in q:
        match q.tag:
            case "restart":
                box.set("Restarting. Try to refresh in a few seconds.")
                await asyncio.sleep(
                    0
                )  # Make sure we send the feedback before the kill()
                try:
                    os.kill(os.getpid(), signal.SIGTERM)
                except Exception as exc:
                    box.print(H.div["error"]("An error occurred"))
                    box.print(H.div["error"](exc))
            case "download":
                pass


ROUTES = app
