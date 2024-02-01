import os

from ..common import FileEditor, YAMLFile, mila_template


@mila_template(help="/help#config")
async def app(page, box):
    """Update the configuration."""
    await FileEditor(YAMLFile(os.environ["PAPERONI_CONFIG"])).run(box)


ROUTES = app
