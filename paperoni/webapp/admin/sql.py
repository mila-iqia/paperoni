import sqlalchemy
from hrepr import H
from starbear import Queue

from ...config import papconf
from ..common import mila_template


@mila_template(help="/help#sql")
async def app(page, box):
    """Query and manipulate the database."""
    q = Queue()

    form = H.form["sql-edit"](
        H.div(H.textarea(name="sql")),
        H.div(H.button("Run")),
        onsubmit=q.wrap(form=True),
    )

    box.print(H.div(form))
    box.print(result_area := H.div().autoid())

    with papconf.database as db:
        async for event in q:
            try:
                result = db.session.execute(event["sql"])
            except Exception as exc:
                page[result_area].set(exc)
                continue

            try:
                t = H.table["sql-results"]()
                t = t(H.tr(H.th(row_name) for row_name in result.keys()))
                t = t(
                    H.tr(
                        H.td(
                            H.code(value.hex())
                            if isinstance(value, bytes)
                            else str(value)
                        )
                        for value in row
                    )
                    for row in result
                )
                page[result_area].set(t)

            except sqlalchemy.exc.ResourceClosedError:
                # Happens when we try to iterate over DELETE results
                page[result_area].set("done")


ROUTES = app
