from pathlib import Path

from aiostream import stream
from hrepr import H
from starbear import Queue, Reference, bear
from starbear.constructors import FormData

from .common import SearchGUI, config, mila_template
from .render import validation_html
from .utils import db_logger

here = Path(__file__).parent


@bear
@mila_template(help="/help#validation")
async def app(page, box):
    """Validate papers."""
    q = Queue()
    action_q = Queue().wrap(form=True, refs=True)
    area = H.div["area"](onchange=action_q).autoid()

    with config().database as db:
        gui = SearchGUI(
            page,
            db,
            q,
            dict(page.query_params),
            defaults={"validation": "not-processed", "limit": 100},
        )
        box.print(gui)
        box.print(
            H.div["helpbox"](
                H.span["ball"]("?"),
                " Please view ",
                H.a(
                    "the help section", href="/help#validation", target="_blank"
                ),
                " for instructions as to how to use this functionality.",
            )
        )
        box.print(area)

        paper_hold = []

        def reset():
            box[area].clear()
            paper_hold.clear()

        async for result in stream.merge(action_q, gui.loop(reset=reset)):
            if isinstance(result, FormData):
                paper = result.ref
                v = result["validation"]
                match v:
                    case "valid":
                        db.remove_flags(paper, "validation")
                        db.insert_flag(paper, "validation", 1)
                    case "invalid":
                        db.remove_flags(paper, "validation")
                        db.insert_flag(paper, "validation", 0)
                    case "unknown":
                        db.remove_flags(paper, "validation")

                user = page.session.get("user", {}).get("email", None)
                db_logger.info(
                    f"User set validation='{v}' on paper {paper.title} "
                    f"({paper.paper_id.hex()})",
                    extra={"user": user},
                )

            else:
                paper_hold.append(result)
                div = validation_html(result)
                existing_flag = db.get_flag(result, "validation")
                val_div = H.div(
                    div,
                    H.form["form-validation"](
                        H.label["validation-button"](
                            H.input(
                                type="radio",
                                name="validation",
                                value="valid",
                                checked=existing_flag == 1,
                            ),
                            "Yes",
                        ),
                        H.label["validation-button"](
                            H.input(
                                type="radio",
                                name="validation",
                                value="invalid",
                                checked=existing_flag == 0,
                            ),
                            "No",
                        ),
                        H.label["validation-button"](
                            H.input(
                                type="radio",
                                name="validation",
                                value="unknown",
                                checked=existing_flag is None,
                            ),
                            "Unknown",
                        ),
                    ),
                    __ref=Reference(result),
                )
                box[area].print(val_div)


ROUTES = app
