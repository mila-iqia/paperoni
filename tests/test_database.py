from paperoni.sql.database import Database
import os


def test_database_creation():
    path = os.path.join(os.path.dirname(__file__), "example.db")
    db = Database(path)
    assert os.path.isfile(path)
    # Check that tables exist.
    for table in (
        "paper",
        "paper_link",
        "author",
        "author_link",
        "author_alias",
        "author_affiliation",
        "venue",
        "release",
        "keyword",
        "paper_to_author",
        "paper_to_release",
        "paper_to_keyword",
    ):
        db.cursor.execute(f"SELECT COUNT(*) FROM {table}")
        assert db.cursor.fetchone()[0] == 0

    # Test insertion.
    db.cursor.execute("INSERT INTO keyword (keyword) VALUES (?)", ["test"])
    db.connection.commit()
    db.cursor.execute("SELECT keyword FROM keyword")
    results = db.cursor.fetchall()
    assert len(results) == 1
    assert results[0][0] == "test"

    # Test deletion.
    db.cursor.execute("DELETE FROM keyword WHERE keyword = ?", ["test"])
    db.connection.commit()
    db.cursor.execute("SELECT COUNT(*) FROM keyword")
    assert db.cursor.fetchone()[0] == 0


def test_date():
    for date in ("2011-01-07", "2009-11-01", "1995-05-15", "2019-11-14"):
        timestamp = Database.date_to_timestamp(date)
        computed_date = Database.timestamp_to_date(timestamp)
        assert date == computed_date, (date, timestamp, computed_date)
