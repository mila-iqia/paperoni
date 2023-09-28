from pathlib import Path

from aiostream import stream
from hrepr import H
from starbear import Queue, bear

from .common import SearchGUI, config, mila_template
from .render import validation_html
from .utils import db_logger, update_logger_handler

here = Path(__file__).parent


@bear
@mila_template(help="/help#validation")
async def app(page, box):
    """Validate papers."""
    q = Queue()
    action_q = Queue().wrap(form=True)
    area = H.div["area"]().autoid()
    papers = {}

    user = page.session.get("user", {}).get("email", None)
    update_logger_handler(db_logger, user)

    with config().database as db:
        gui = SearchGUI(
            page,
            db,
            q,
            dict(page.query_params),
            defaults={"no-validation": True},
        )
        box.print(gui)
        box.print(area)

        async for result in stream.merge(
            action_q, gui.loop(reset=box[area].clear)
        ):
            if isinstance(result, dict):
                for k, v in result.items():
                    if k.startswith("v-"):
                        paper_id = k.removeprefix("v-")
                        paper = papers[paper_id]
                        match v:
                            case "valid":
                                db.insert_flag(paper, "validation", 1)
                            case "invalid":
                                db.insert_flag(paper, "validation", 0)
                            case "unknown":
                                db.remove_flags(paper, "validation")

            else:
                div = validation_html(result)
                pid = result.paper_id.hex()
                papers[pid] = result
                existing_flag = db.get_flag(result, "validation")
                val_div = H.div(
                    div,
                    H.form["form-validation"](
                        H.label["validation-button"](
                            H.input(
                                type="radio",
                                name=f"v-{pid}",
                                value="valid",
                                checked=existing_flag == 1,
                                onchange=action_q,
                            ),
                            "Yes",
                        ),
                        H.label["validation-button"](
                            H.input(
                                type="radio",
                                name=f"v-{pid}",
                                value="invalid",
                                checked=existing_flag == 0,
                                onchange=action_q,
                            ),
                            "No",
                        ),
                        H.label["validation-button"](
                            H.input(
                                type="radio",
                                name=f"v-{pid}",
                                value="unknown",
                                checked=existing_flag is None,
                                onchange=action_q,
                            ),
                            "Unknown",
                        ),
                    ),
                )
                box[area].print(val_div)


ROUTES = app
