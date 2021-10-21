from paperoni.sql.database import Database
import os


def test_database_creation():
    path = os.path.join(os.path.dirname(__file__), "example.db")
    db = Database(path)
    assert os.path.isfile(path)
    for table in (
        "paper",
        "paper_external_id",
        "paper_url",
        "author",
        "author_external_id",
        "author_alias",
        "author_affiliation",
        "author_url",
        "venue",
        "release",
        "field_of_study",
        "paper_to_author",
        "paper_to_release",
        "paper_to_field_of_study",
    ):
        db.cursor.execute(f"SELECT COUNT(*) FROM {table}")
        assert db.cursor.fetchone()[0] == 0
