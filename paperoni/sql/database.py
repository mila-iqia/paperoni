import os
import sqlite3
from typing import Sequence
from datetime import datetime


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

    def modify(self, query, parameters=()):
        """
        Execute a modification query (INSERT, UPDATE, etc).
        Return last inserted row ID, or None if no row was inserted.
        """
        self.cursor.execute(query, parameters)
        self.connection.commit()
        return self.cursor.lastrowid

    def insert(self, table: str, columns: Sequence[str], values: Sequence):
        """Insert a row in a table and return new row ID."""
        assert len(columns) == len(values)
        return self.modify(
            f"INSERT INTO {table} ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' * len(columns))})",
            values,
        )

    def select_id(self, table, column, where_query, where_parameters=()):
        """
        Select one ID from a table and return it if found, else None.
        If more than 1 ID is found, raise a RuntimeError.
        """
        assert None not in where_parameters
        self.cursor.execute(
            f"SELECT {column} FROM {table} WHERE {where_query}",
            where_parameters,
        )
        results = self.cursor.fetchall()
        if len(results) == 0:
            return None
        elif len(results) == 1:
            return results[0][0]
        else:
            raise RuntimeError(
                f"Found {len(results)} entries for {table}.{column}"
            )

    def count(self, table, column, where_query, where_parameters=()):
        """Select and return count from a table."""
        assert None not in where_parameters
        self.cursor.execute(
            f"SELECT COUNT({column}) FROM {table} WHERE {where_query}",
            where_parameters,
        )
        return self.cursor.fetchone()[0]

    @classmethod
    def date_to_timestamp(cls, date: str) -> int:
        return round(datetime.strptime(date, "%Y-%m-%d").timestamp())

    @classmethod
    def timestamp_to_date(cls, timestamp: int) -> str:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
