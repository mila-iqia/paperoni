from ..common import ConfigEditor, mila_template


@mila_template(help="/help#tokens")
async def __app__(page, box):
    """Update tokens."""
    file = page.server_instance.plugins["tokens"]
    box.print(ConfigEditor(file))
