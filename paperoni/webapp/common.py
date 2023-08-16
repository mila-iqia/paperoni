from datetime import datetime

from sqlalchemy import select

from paperoni.db import schema as sch

from ..cli_helper import search_stmt


def search_interface(event=None, db=None):
    def regen(event=None):
        title, author, venue, date_start, date_end = (
            None,
            None,
            None,
            None,
            None,
        )
        if event is not None and event:
            if "title" in event.keys():
                title = event["title"]
            if (
                "value" in event.keys()
            ):  # If the name of the input (event key) is not specified, the default value will be the title
                title = event["value"]
            if "author" in event.keys():
                author = event["author"]
            if "venue" in event.keys():
                venue = event["venue"]
            if "date-start" in event.keys():
                date_start = event["date-start"]
            if "date-end" in event.keys():
                date_end = event["date-end"]

        stmt = search_stmt(
            title=title,
            author=author,
            venue=venue,
            start=date_start,
            end=date_end,
        )
        try:
            for (r,) in db.session.execute(stmt):
                yield r
        except Exception as e:
            print("Error : ", e)

    return regen(event=event)
