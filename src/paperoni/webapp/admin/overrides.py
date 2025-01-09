import gifnoc
import yaml

from ...config import papconf
from ..common import ConfigEditor, mila_template


class ConfigFile:
    def __init__(self, file):
        self.file = file

    def read(self):
        return self.file.read_text()

    def write(self, new_permissions, dry=False):
        d = yaml.safe_load(new_permissions)
        with gifnoc.overlay(d):
            pass
        if not dry:
            self.file.write_text(new_permissions)
            gifnoc.current_configuration().refresh()


@mila_template(help="/help#overrides")
async def __app__(page, box):
    """Update overrides."""
    file = ConfigFile(papconf.paths.database.parent / "overrides.yaml")
    box.print(ConfigEditor(file, language="yaml"))
