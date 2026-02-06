import math
import time
from dataclasses import dataclass, field, replace
from datetime import date as _date, timedelta

import gifnoc
from fastapi import Depends, Request
from serieux import deserialize, serialize

from ..__main__ import Coll
from ..collection.abc import PaperCollection
from ..model import Paper
from ..operations import operation
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
                if (
                    r.peer_review_status == "peer-reviewed"
                    and p.info.get("peer_reviewed_serial", math.inf) > self.serial
                ):
                    peer_reviewed.append(p)
                    break
                elif (
                    r.peer_review_status in {"preprint", "workshop"}
                    and p.info.get("preprint_serial", math.inf) > self.serial
                ):
                    preprints.append(p)
                    break

        return {
            "peer-reviewed": peer_reviewed,
            "preprints": preprints,
        }


@dataclass
class NewsletterConfig:
    latest: LatestGenerator = field(default_factory=LatestGenerator)


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
        updates = []

        for p in result["peer-reviewed"]:
            updates.append(replace(p, info={**p.info, "peer_reviewed_serial": generator.serial}))

        for p in result["preprints"]:
            updates.append(replace(p, info={**p.info, "preprint_serial": generator.serial}))

        await coll.collection.add_papers(updates, force=True, ignore_exclusions=True)

        return {"success": True}


@operation
def clear_serials(p: Paper):
    info = dict(p.info)
    info.pop("peer_reviewed_serial", None)
    info.pop("preprint_serial", None)
    return replace(p, info=info)


config = gifnoc.define("paperoni.newsletter", NewsletterConfig)
