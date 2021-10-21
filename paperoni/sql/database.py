import os
import sqlite3


class Database:
    __slots__ = ("connection", "cursor")
    DATABASE_SCRIPT_FILE = os.path.join(
        os.path.dirname(__file__), "database.sql"
    )

    def __init__(self, path: str):
        """
        Open (or create) and populate tables (if necessary)
        in database at given path.
        """
        self.connection = sqlite3.connect(path)
        self.cursor = self.connection.cursor()
        with open(self.DATABASE_SCRIPT_FILE) as script_file:
            self.cursor.executescript(script_file.read())
            self.connection.commit()
