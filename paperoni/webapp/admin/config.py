import os

from starbear import bear

from ..common import FileEditor, YAMLFile, mila_template


@bear
@mila_template
async def app(page, box):
    """Update the configuration."""
    await FileEditor(YAMLFile(os.environ["PAPERONI_CONFIG"])).run(box)


ROUTES = app
