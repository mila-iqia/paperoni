import math
import time
from dataclasses import dataclass, field, replace
from datetime import date as _date, timedelta

import gifnoc
from fastapi import Depends, Request
from hrepr import H
from mailchimp_marketing import Client
from serieux import deserialize, serialize
from serieux.features.encrypt import Secret

from ..__main__ import Coll
from ..collection.abc import PaperCollection
from ..model import DatePrecision, Paper
from ..operations import operation
from ..utils import expand_links_dict
from ..web.helpers import render_template


@dataclass
class LatestGenerator:
    forward: int = 0
    back: int = 30
    serial: int = 0
    date: _date = None

    def __post_init__(self):
        if self.date is None:
            self.date = _date.today()

    @property
    def start(self):
        """Start date: self.date minus self.back days."""
        return self.date - timedelta(days=self.back)

    @property
    def end(self):
        """End date: self.date plus self.forward days."""
        return self.date + timedelta(days=self.forward)

    async def __call__(self, coll: PaperCollection):
        peer_reviewed = []
        preprints = []

        async for p in coll.search(start_date=self.start, end_date=self.end):
            relevant_releases = [
                r
                for r in p.releases
                if r.venue.date and self.start <= r.venue.date <= self.end
            ]
            for r in relevant_releases:
                prs = r.peer_review_status
                ispr = (
                    prs == "peer-reviewed"
                    and p.info.get("peer_reviewed_serial", math.inf) > self.serial
                )
                ispre = (
                    prs in {"preprint", "workshop"}
                    and p.info.get("preprint_serial", math.inf) > self.serial
                )
                if ispr:
                    peer_reviewed.append(p)
                    break
                elif ispre:
                    preprints.append(p)
                    break

        return {
            "peer-reviewed": peer_reviewed,
            "preprints": preprints,
        }


@dataclass
class Campaign:
    # Title of the campaign
    title: str
    # Preview text
    preview_text: str
    # Reply-to line
    reply_to: str
    # From line
    from_name: str
    # Subject line
    subject: str
    # List id
    list_id: str
    # Template id
    template_id: int
    # Language
    lang: str
    # Segment id
    segment_id: int | None = None
    # Link
    link: str | None = None


@dataclass
class Mail:
    # Mailchimp token
    token: Secret[str]
    # Mailchimp server
    server: str
    # Campaigns
    campaigns: dict[str, Campaign]
    # Localization strings
    localization: dict[str, dict[str, str]]
    # Whether to send a test email
    send_test: bool
    # Recipients for test email
    test_recipients: list[str]
    # Name for the template's main section
    template_main_section: str
    # Name for the template's link section
    template_link_section: str
    # Folder id
    folder_id: str
    # Number of days to look back by default
    default_window: int

    def generate_campaign(self, generator, peer_reviewed, preprints):
        if not peer_reviewed and not preprints:
            return {
                "status": "failure",
                "reason": "The list of papers to send is empty!",
            }

        mch = Client()
        mch.set_config({"api_key": self.token, "server": self.server})

        campaigns = {}
        response = {}

        for name, cpg in self.campaigns.items():
            recipients = {"list_id": cpg.list_id}
            if cpg.segment_id:
                recipients["segment_opts"] = {
                    "saved_segment_id": cpg.segment_id,
                }

            resp = mch.campaigns.create(
                {
                    "type": "regular",
                    "settings": {
                        "title": cpg.title,
                        "subject_line": f"{cpg.subject} - {generator.end.strftime('%Y-%m-%d')}",
                        "preview_text": cpg.preview_text,
                        "from_name": cpg.from_name,
                        "reply_to": cpg.reply_to,
                        "to_name": "*|FNAME|* *|LNAME|*",
                        "inline_css": True,
                        "template_id": cpg.template_id,
                    },
                    "recipients": recipients,
                }
            )
            campaigns[name] = (None, cpg, resp)
            # lbox.print(H.div(f"Campaign {resp['id']} created"))
            web_id = resp["web_id"]
            url = f"https://us2.admin.mailchimp.com/campaigns/edit?id={web_id}"
            response[name] = {
                "url": url,
                "archive": resp["archive_url"],
            }

        for name, (_, cpg, resp) in campaigns.items():
            html_to_send = latest_html(peer_reviewed, preprints, cpg.lang)
            arch = campaigns[cpg.link][2]["archive_url"] if cpg.link else None
            link_text = self.localization["link"][cpg.lang]
            mch.campaigns.set_content(
                resp["id"],
                {
                    "template": {
                        "id": cpg.template_id,
                        "sections": {
                            self.template_main_section: str(html_to_send),
                            self.template_link_section: f'<a href="{arch}">{link_text}</a>'
                            if arch
                            else "",
                        },
                    }
                },
            )

        return {
            "status": "success",
            "links": response,
        }


@dataclass
class NewsletterConfig:
    latest: LatestGenerator = field(default_factory=LatestGenerator)
    mail: Mail = None


def join(elems, sep=", ", lastsep=None):
    """Create a list using the given separators.

    If lastsep is None, lastsep = sep.

    Returns:
        [elem0, (sep, elem1), (sep, elem2), ... (lastsep, elemn)]
    """
    if lastsep is None:
        lastsep = sep
    elems = list(elems)
    if len(elems) <= 1:
        return elems
    results = [elems[0]]
    for elem in elems[1:-1]:
        results.extend((H.raw(sep), elem))
    results.extend((H.raw(lastsep), elems[-1]))
    return results


def paper_html(paper, maxauth=20):
    venues = H.div["venues"]
    for release in paper.releases:
        v = release.venue
        venues = venues(
            H.div["venue"](
                H.span["venue-name"](v.name),
                " (",
                H.span["venue-date"](DatePrecision.format(v.date, v.date_precision)),
                ")",
            )
        )
        break

    nauth = len(paper.authors)
    more = nauth - maxauth if nauth > maxauth else 0

    links = expand_links_dict(paper.links)
    pdfs = [lnk["url"] for lnk in links if "pdf" in lnk.get("url", "")]
    links = [lnk["url"] for lnk in links if "url" in lnk]

    return H.div["paper"](
        H.div["content"](
            H.div["title"](
                H.a(paper.title, href=links[0], target="_blank")
                if links
                else paper.title,
                H.span["pdf-link"](
                    " [",
                    H.a(
                        "PDF",
                        href=pdfs[0],
                        target="_blank",
                    ),
                    "]",
                )
                if pdfs
                else "",
            ),
            H.div["authors"](
                join([auth.author.name for auth in paper.authors[:maxauth]]),
                f"... ({more} more)" if more else "",
            ),
            H.div["topics"](join([t.name for t in paper.topics])),
            venues,
        ),
    )


def latest_html(peers, preprints, lang):
    return H.div(
        H.h2(config.mail.localization["peer-reviewed"][lang]) if peers else "",
        [paper_html(paper) for paper in peers],
        H.h2(config.mail.localization["preprint"][lang]) if preprints else "",
        [paper_html(paper) for paper in preprints],
    )


def install_latest(app):
    hascap = app.auth.get_email_capability

    @app.get("/latest-group")
    async def latest_group_page(
        request: Request,
        user: str = Depends(hascap("validate", redirect=True)),
    ):
        """Render the latest group page."""
        validate = deserialize(app.auth.capabilities.captype, "validate")
        is_validator = app.auth.capabilities.check(user, validate)
        return render_template(
            "latest-group.html",
            request,
            is_validator=is_validator,
            default_ndays=config.latest.back,
            default_fwd=config.latest.forward,
            default_serial=int(time.time()),
        )

    @app.get("/api/v1/latest", dependencies=[Depends(hascap("validate"))])
    async def get_latest(generator: LatestGenerator = Depends()):
        """Get latest papers using LatestGenerator."""
        coll = Coll(command=None)
        result = await generator(coll.collection)
        return serialize(dict[str, list[Paper]], result)

    @app.post("/latest-group/generate", dependencies=[Depends(hascap("validate"))])
    async def generate_latest(generator: LatestGenerator = Depends()):
        """Generate newsletter content from latest papers."""
        coll = Coll(command=None)
        result = await generator(coll.collection)

        response = config.mail.generate_campaign(
            generator, result["peer-reviewed"], result["preprints"]
        )
        if response["status"] != "success":
            return response

        updates = []
        for p in result["peer-reviewed"]:
            updates.append(
                replace(
                    p,
                    info={
                        **p.info,
                        "peer_reviewed_serial": generator.serial,
                        "preprint_serial": generator.serial,
                    },
                )
            )

        for p in result["preprints"]:
            updates.append(
                replace(p, info={**p.info, "preprint_serial": generator.serial})
            )

        await coll.collection.add_papers(updates, force=True, ignore_exclusions=True)
        return response


@operation
def clear_serials(p: Paper):
    info = dict(p.info)
    info.pop("peer_reviewed_serial", None)
    info.pop("preprint_serial", None)
    return replace(p, info=info)


config = gifnoc.define("paperoni.newsletter", NewsletterConfig)
