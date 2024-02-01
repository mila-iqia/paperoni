from ..common import LogsViewer, config, mila_template


@mila_template(help="/help#logs")
async def app(page, box):
    """Monitor systemd logs."""
    try:
        services = config().services
    except AttributeError:
        services = []
    await LogsViewer(services).run(box)


ROUTES = app
