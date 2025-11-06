from dataclasses import dataclass, field
from datetime import datetime

import gifnoc
from gifnoc import Command
from hrepr import H, Tag
from mailchimp_marketing import Client

from .cli_helper import search
from .display import expand_links, join
from .mila_upload import Search
from .model import DatePrecision
from .utils import sort_releases


@dataclass
class Campaign:
    # Title of the campaign
    title: str
    # Preview text
    preview_text: str
    # Reply-to line
    reply_to: str
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
class MailOptions:
    # Mailchimp token
    token: str
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


mchimp_options = gifnoc.define(
    field="paperoni.mchimp_options",
    model=MailOptions,
)


def mail_html(paper, maxauth=20):
    venues = H.div["venues"]
    for release, _ in sort_releases(paper.releases):
        v = release.venue
        venues = venues(
            H.div["venue"](
                H.span["venue-name"](v.name),
                " (",
                H.span["venue-date"](
                    DatePrecision.format(v.date, v.date_precision)
                ),
                ")",
            )
        )
        break

    nauth = len(paper.authors)
    more = nauth - maxauth if nauth > maxauth else 0

    links = expand_links(paper.links)
    pdfs = [lnk for k, lnk in links if "pdf" in lnk]

    return H.div["paper"](
        H.div["content"](
            H.div["title"](
                H.a(paper.title, href=links[0][1], target="_blank")
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


@dataclass
class GenerationResult:
    html: Tag = None
    peers: list = field(default_factory=list)
    preprints: list = field(default_factory=list)


def generate_latest_html(start, end, serial, lang):
    query = Search(
        start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d")
    )

    result = GenerationResult()

    for paper in search(**vars(query)):
        valid = any(
            flag.flag
            for flag in paper.paper_flag
            if flag.flag_name == "validation"
        )
        if not valid:
            continue
        releases = sort_releases(paper.releases)
        if not releases:
            continue
        main_release, order = releases[0]
        vdate = datetime.fromtimestamp(main_release.venue.date)
        if vdate < start or vdate > end:
            continue
        peer_send = paper.latest_send["peer_reviewed"]
        if peer_send < serial:
            continue
        if order >= 1:
            result.peers.append(paper)
        elif order >= -1:
            pre_send = paper.latest_send["preprint"]
            if pre_send < serial:
                continue
            result.preprints.append(paper)

    result.html = H.div(
        H.h2(mchimp_options.localization["peer-reviewed"][lang])
        if result.peers
        else "",
        [mail_html(paper) for paper in result.peers],
        H.h2(mchimp_options.localization["preprint"][lang])
        if result.preprints
        else "",
        [mail_html(paper) for paper in result.preprints],
    )
    return result


def command_mchimp(argv):
    with gifnoc.cli(
        options=Command(
            mount="paperoni.mchimp_options",
            auto=True,
        ),
        argv=argv,
    ):
        opt = mchimp_options
        mch = Client()
        mch.set_config({"api_key": opt.token, "server": opt.server})
        raise NotImplementedError("There is no CLI command yet.")
