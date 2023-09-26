from starbear import bear

from ..common import FileEditor, mila_template


@bear
@mila_template(help="/help#permissions")
async def app(page, box):
    """Update permissions."""
    await FileEditor(page.app.grizzlaxy.permissions).run(box)


ROUTES = app
