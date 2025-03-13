from datetime import datetime, timedelta
from pathlib import Path

from hrepr import H
from mailchimp_marketing import Client
from sqlalchemy import func
from starbear import Queue

from ..config import papconf
from ..db import schema as sch
from ..mila_mchimp import generate_latest_html, mchimp_options
from .common import mila_template

here = Path(__file__).parent


@mila_template(help="/help#latest")
async def __app__(page, box):
    """List latest papers."""
    q = Queue()

    mcss = here / "mail.css"
    page.add_resources(mcss)

    def refresh():
        nonlocal result
        fwd = 30
        if end_date:
            _end = datetime.strptime(end_date, "%Y-%m-%d")
            _start = _end - timedelta(days=days)
        else:
            _end = datetime.now() + timedelta(days=fwd)
            _start = _end - timedelta(days=days + fwd)

        targ = page[area]
        targ.clear()
        result = generate_latest_html(_start, _end, serial)
        targ.print(result.html)

    def send():
        nonlocal serial

        cbox = H.div["campaign"]().ensure_id()
        page[campaign_area].set(cbox)
        cbox = page[cbox]

        def line(x, bold=False):
            if bold:
                x = H.b(x)
            cbox.print(H.div(x))

        line(H.h3(f"Generate campaign #{serial}"))

        opt = mchimp_options
        mch = Client()
        mch.set_config({"api_key": opt.token, "server": opt.server})

        campaigns = {}

        if not result.peers and not result.preprints:
            line(H.h3("FAILURE: The list of papers to send is empty!"))
            return

        for name, cpg in opt.campaigns.items():
            lbox = H.div["campaign-letter"]().ensure_id()
            line(lbox)
            lbox = page[lbox]
            lbox.print(H.div(H.b(f"{name}"), " -- ", cpg.title))
            resp = mch.campaigns.create(
                {
                    "type": "regular",
                    "settings": {
                        "title": cpg.title,
                        "subject_line": "Publications",
                        "preview_text": cpg.preview_text,
                        "from_name": "Mila",
                        "reply_to": cpg.reply_to,
                        "to_name": "*|FNAME|* *|LNAME|*",
                        "inline_css": True,
                        # "folder_id": opt.folder_id,
                        "template_id": cpg.template_id,
                    },
                    "recipients": {
                        "list_id": cpg.list_id,
                        "segment_opts": {
                            "saved_segment_id": cpg.segment_id,
                        },
                    },
                }
            )
            campaigns[name] = (lbox, cpg, resp)
            lbox.print(H.div(f"Campaign {resp['id']} created"))
            web_id = resp["web_id"]
            url = f"https://us2.admin.mailchimp.com/campaigns/edit?id={web_id}"
            lbox.print(
                H.div(H.a("Link to campaign", target="_blank", href=url))
            )
            lbox.print(
                H.div(
                    H.a(
                        "Link to archive",
                        target="_blank",
                        href=resp["archive_url"],
                    )
                )
            )

        # html_to_send = H.div(H.style(mcss.read_text()), result.html)
        html_to_send = result.html

        for name, (lbox, cpg, resp) in campaigns.items():
            arch = campaigns[cpg.link][1]["archive_url"] if cpg.link else None
            mch.campaigns.set_content(
                resp["id"],
                {
                    "template": {
                        "id": cpg.template_id,
                        "sections": {
                            opt.template_main_section: str(html_to_send),
                            opt.template_link_section: f'<a href="{arch}">{cpg.link_text}</a>'
                            if arch
                            else "",
                        },
                    }
                },
            )
            lbox.print(H.div("Content set!"))
            lbox.print(H.div("DONE."))

        sends = []
        for paper in result.peers:
            sends.append(
                sch.PaperSent(
                    paper_id=paper.paper_id,
                    peer_reviewed=1,
                    serial_number=serial,
                )
            )
        for paper in result.preprints:
            sends.append(
                sch.PaperSent(
                    paper_id=paper.paper_id,
                    peer_reviewed=0,
                    serial_number=serial,
                )
            )
        for send in sends:
            db.session.merge(send)
        db.session.commit()
        serial += 1

        refresh()

    with papconf.database as db:
        days = 7
        max_query = db.session.query(func.max(sch.PaperSent.serial_number))
        try:
            ((max_serial,),) = list(db.session.execute(max_query))
        except ValueError:
            max_serial = 0

        serial = (max_serial or 0) + 1
        end_date = ""

        result = None
        area = H.div["area"].ensure_id()
        campaign_area = H.div().ensure_id()

        page.print(
            H.form["latest"](
                H.div(
                    H.label("Days: "),
                    H.input(value=str(days), name="days"),
                ),
                H.div(
                    H.label("Serial: "),
                    H.input(value=str(serial), name="serial"),
                ),
                H.div(
                    H.label("End date: "),
                    H.input(value=end_date, name="end_date"),
                ),
                H.div(H.button("Generate campaign", name="generate")),
                oninput=q.wrap(form=True),
                onsubmit=q.wrap(form=True),
            )
        )
        page.print(campaign_area)
        page.print(area)

        refresh()
        async for event in q:
            if event.submit:
                send()

            else:
                try:
                    days = int(event["days"])
                    serial = int(event["serial"])
                    end_date = event["end_date"]
                    refresh()
                except Exception as exc:
                    page[area].set(f"{type(exc).__name__}: {exc}")
