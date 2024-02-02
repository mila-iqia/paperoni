from ..common import FileEditor, mila_template


@mila_template(help="/help#permissions")
async def app(page, box):
    """Update permissions."""
    # yikes.
    await FileEditor(page.instance.mother.app.grizzlaxy.permissions).run(box)


ROUTES = app
