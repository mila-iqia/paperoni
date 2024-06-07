import asyncio
import os
import shutil
import signal
from tempfile import mkstemp

from grizzlaxy import simple_route
from hrepr import H
from starbear import Queue
from starlette.responses import PlainTextResponse

from ...config import papconf
from ..common import mila_template


@mila_template(help="/help#operations")
async def app(page, box):
    """Admin operations."""
    q = Queue()

    box.print(H.p(H.button("Restart server", onclick=q.tag("restart"))))
    box.print(H.p(H.button("Upload to website", onclick=q.tag("web-upload"))))
    # for service_name, service in (papconf.services or {}).items():
    #     status = "" if service.enabled else " (disabled)"
    #     box.print(
    #         H.p(
    #             H.button(
    #                 f"Run service: {service_name}{status}",
    #                 onclick=q.tag(f"service:{service_name}"),
    #             ),
    #             id=service_name,
    #         )
    #     )
    box.print(H.p(H.a("Download database", href=papconf.paths.database)))
    box.print(
        H.p(
            H.form(
                H.strong("DANGER! "),
                H.label("Reupload entire database ", **{"for": "upload"}),
                H.input(type="file", name="filename"),
                H.input(type="submit"),
                action="/admin/operations/database-upload",
                method="post",
                enctype="multipart/form-data",
            )
        )
    )

    async for event in q:
        match event.tag:
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
            case "web-upload":
                box.print(H.div("Running web upload..."))
                proc = await asyncio.create_subprocess_shell(
                    "paperoni misc upload",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if stdout:
                    box.print(H.div("<stdout>"))
                    box.print(H.pre(stdout.decode("utf8")))
                if stderr:
                    box.print(H.div("<stderr>"))
                    box.print(H.pre(stderr.decode("utf8")))
                box.print(H.div("Done with web upload!"))
            # case service:
            #     service = service.split("service:")[-1]
            #     try:
            #         result = subprocess.run(["systemctl", "start", service])
            #     except FileNotFoundError:
            #         page[f"#{service}"].set("systemctl is not available")
            #         continue
            #     if result.returncode != 0:
            #         page[f"#{service}"].set(
            #             f"There was an error (return code: {result.returncode})"
            #         )
            #     else:
            #         page[f"#{service}"].set(f"Requested {service} to run")


@simple_route(methods=["POST"])
async def database_upload(request):
    async with request.form() as form:
        _, tmpfile = mkstemp()
        with open(tmpfile, "wb") as dest:
            while True:
                contents = await form["filename"].read(2**20)
                if not contents:
                    break
                dest.write(contents)
        os.remove(papconf.paths.database)
        shutil.move(tmpfile, papconf.paths.database)
        return PlainTextResponse(
            "Uploaded. You might want to restart the server."
        )


database_upload.hidden = True


ROUTES = {
    "/": app,
    "/database-upload": database_upload,
}
