from paperoni.db import schema as sch
from datetime import datetime
from sqlalchemy import select
from ..cli_helper import search_stmt

def search_interface(event=None,db=None):
    def regen(event=None):
            title,author,venue,date_start,date_end = None,None,None,None,None
            if event is not None and event:
                if "title" in event.keys():
                    title = event["title"]
                if "value" in event.keys(): #If the name of the input (event key) is not specified, the default value will be the title
                    title = event["value"] 
                if "author" in event.keys():
                    author = event["author"]
                if "venue" in event.keys():
                    venue = event["venue"]
                if "date-start" in event.keys():
                    date_start = event["date-start"]
                if "date-end" in event.keys():
                    date_end = event["date-end"]
           
            stmt = search_stmt(title=title, author=author, venue=venue, start=date_start, end=date_end)
            try:
                for (r,) in db.session.execute(stmt):
                    yield r
            except Exception as e:
                print("Error : ", e)

    def search(title, author, date_start, date_end):
        print("in search")
        stmt = select(sch.Paper)
        # Selecting from the title
        if title is not None and title != "":
            stmt = select(sch.Paper).filter(sch.Paper.title.like(f"%{title}%"))
        # Selecting from author
        if author is not None and author != "":
            stmt = (
                stmt.join(sch.Paper.paper_author)
                .join(sch.PaperAuthor.author)
                .filter(sch.Author.name.like(f"%{author}%"))
            )
        # Selecting from date
        # Joining the tables if any of the dates are set
        if (date_start is not None and date_start != "") or (
            date_end is not None and date_end != ""
        ):
            stmt = stmt.join(sch.Paper.release).join(sch.Release.venue)
        # Filtering for the dates
        if date_start is not None and date_start != "":
            date_start_stamp = int(
                datetime(*map(int, date_start.split("-"))).timestamp()
            )
            stmt = stmt.filter(sch.Venue.date >= date_start_stamp)
        if date_end is not None and date_end != "":
            date_end_stamp = int(
                datetime(*map(int, date_end.split("-"))).timestamp()
            )
            stmt = stmt.filter(sch.Venue.date <= date_end_stamp)
        return stmt
    
    return regen(event=event)