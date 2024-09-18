from ..common import FileEditor, mila_template


@mila_template(help="/help#permissions")
async def __app__(page, box):
    """Update permissions."""
    # yikes.
    await FileEditor(page.server_instance.plugins["permissions"].permissions).run(box)
