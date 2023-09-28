from datetime import datetime

from starlette.responses import JSONResponse, StreamingResponse

from ..db.model_export import export
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
        now = datetime.now().strftime("%Y-%M-%D")
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
        return export(paper).tagged_json()


class CSVFormatter(PaperFormatter):
    def __init__(self):
        super().__init__(pre="", join="\n", post="", media_type="text/csv")

    def destination(self):
        dest = super().destination()
        return f"{dest}.csv"

    def process(self, paper):
        return paper.title


formatters = {
    "json": JSONFormatter(),
    "csv": CSVFormatter(),
}


async def report(request):
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


ROUTES = report
