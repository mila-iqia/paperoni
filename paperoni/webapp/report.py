import json
from datetime import datetime

from starlette.responses import JSONResponse, StreamingResponse

from ..cli_helper import ExtendAttr
from ..display import expand_links
from ..export import export
from .common import SearchGUI, config


class PaperFormatter:
    def __init__(self, pre="", join="", post="", media_type="text/plain"):
        self.pre = pre
        self.join = join
        self.post = post
        self.media_type = media_type

    def process(self, paper):
        return paper.title

    def destination(self):
        now = datetime.now().strftime("%Y-%m-%d")
        return f"paperoni-{now}"

    async def generate(self, params):
        with config().database as db:
            fake_gui = SearchGUI(
                page=None,
                db=db,
                queue=None,
                params=params,
                defaults={"limit": 0, "sort": "-date"},
            )
            yield self.pre
            for i, paper in enumerate(fake_gui.regen()):
                if i > 0:
                    yield self.join
                yield self.process(paper)
            yield self.post


class JSONFormatter(PaperFormatter):
    def __init__(self):
        super().__init__(pre="[", join=",", post="]", media_type="text/json")

    def destination(self):
        dest = super().destination()
        return f"{dest}.json"

    def process(self, paper):
        return json.dumps(export(paper))


class CSVFormatter(PaperFormatter):
    def __init__(self):
        fields = [
            "title",
            "authors",
            "venue",
            "date",
            "status",
            "link",
            "pdf",
            "excerpt",
        ]
        super().__init__(
            pre=",".join(fields) + "\n",
            join="\n",
            post="\n",
            media_type="text/csv",
        )

    def quote(self, s):
        s = str(s)
        if '"' in s:
            s = s.replace('"', r"\"")
        if "," in s or "\n" in s or '"' in s:
            s = f'"{s}"'
        return s

    def destination(self):
        dest = super().destination()
        return f"{dest}.csv"

    def process(self, paper):
        rels = [
            rel
            for rel in paper.releases
            if rel.status not in ("submitted", "preprint")
        ] or paper.releases
        lnks = expand_links(paper.links)
        pdfs = [url for ty, url in lnks if ty.endswith("pdf")]
        row = {
            "title": paper.title,
            "authors": ",".join(a.author.name for a in paper.authors),
            "venue": rels[0].venue.name,
            "date": datetime.fromtimestamp(rels[0].venue.date).strftime(
                "%Y-%m-%d"
            ),
            "status": rels[0].status,
            "link": lnks[0][1],
            "pdf": pdfs[0] if pdfs else "",
            "excerpt": "".join(getattr(paper, "excerpt", ("", "", ""))),
        }
        return ",".join(map(self.quote, row.values()))


formatters = {
    "json": JSONFormatter(),
    "csv": CSVFormatter(),
}


async def report(request):
    """Generate a JSON or CSV report."""
    fmt = request.query_params.get("format", "json")
    formatter = formatters.get(fmt, None)
    if formatter is None:
        return JSONResponse(
            {"error": f"Unknown format: {fmt}"},
            status_code=400,
        )

    return StreamingResponse(
        formatter.generate(dict(request.query_params)),
        media_type=formatter.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{formatter.destination()}"',
        },
    )


report.hidden = True

ROUTES = report
