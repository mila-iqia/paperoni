import os

from starbear import bear

from ..common import FileEditor, YAMLFile, mila_template


@bear
@mila_template(title="Update the configuration", help="/help#config")
async def app(page, box):
    """Update the configuration."""
    await FileEditor(YAMLFile(os.environ["PAPERONI_CONFIG"])).run(box)


ROUTES = app
