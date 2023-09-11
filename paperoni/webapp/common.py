import traceback

from ..cli_helper import search


def search_interface(event=None, db=None):
    def regen(event=None):
        title, author, venue, date_start, date_end, excerpt = (
            None,
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
            if "excerpt" in event.keys():
                excerpt = event["excerpt"]

        results = search(
            title=title,
            author=author,
            venue=venue,
            start=date_start,
            end=date_end,
            excerpt=excerpt,
            allow_download=False,
        )
        try:
            yield from results
        except Exception as e:
            traceback.print_exception(e)

    return regen(event=event)
