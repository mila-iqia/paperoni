from ...config import papconf
from ..common import LogsViewer, mila_template


@mila_template(help="/help#logs")
async def __app__(page, box):
    """Monitor systemd logs."""
    services = papconf.services or {}
    await LogsViewer(services).run(box)
