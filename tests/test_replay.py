def test_replay(config_empty):
    def check():
        with config_empty.database as db:
            results = list(
                db.session.execute(
                    'SELECT title FROM paper WHERE title LIKE "%Machine Learning%"'
                )
            )
            return results == [
                (
                    "Machine Learning for Combinatorial Optimization: a Methodological Tour d'Horizon",
                )
            ]

    assert not check()
    config_empty.database.replay(before="90")
    assert check()
