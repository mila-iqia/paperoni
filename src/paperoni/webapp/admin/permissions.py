from ..common import ConfigEditor, mila_template


@mila_template(help="/help#permissions")
async def __app__(page, box):
    """Update permissions."""
    file = page.server_instance.plugins["permissions"].permissions
    box.print(ConfigEditor(file))
