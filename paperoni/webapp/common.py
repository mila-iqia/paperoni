import asyncio
import os
import traceback
from functools import wraps
from pathlib import Path
from urllib.parse import urlencode

import yaml
from grizzlaxy.index import render
from hrepr import H
from starbear import ClientWrap, Queue, template as _template
from starbear.serve import LoneBear

from ..cli_helper import search
from ..config import config as config_var, load_config
from ..utils import keyword_decorator

here = Path(__file__).parent


class NormalFile:
    def __init__(self, pth, validate=None):
        self.path = Path(pth).expanduser()
        self.validate = validate

    def read(self):
        return self.path.read_text()

    def write(self, new_text, dry=False):
        if self.validate:
            if not self.validate(new_text):
                raise Exception(f"Content is invalid")
        if not dry:
            self.path.write_text(new_text)


class YAMLFile(NormalFile):
    def __init__(self, pth):
        super().__init__(pth, yaml.safe_load)


class FileEditor:
    def __init__(self, file):
        self.file = file

    async def run(self, page):
        q = Queue()
        submit = ClientWrap(q, form=True)
        debounced = ClientWrap(q, debounce=0.3, form=True)

        page.print(
            H.form["update-file"](
                H.textarea(
                    self.file.read(), name="new-content", oninput=debounced
                ),
                actionarea := H.div().autoid(),
                onsubmit=submit,
            ),
        )

        async for event in q:
            submitting = event["$submit"]
            try:
                self.file.write(event["new-content"], dry=not submitting)
            except Exception as exc:
                page[actionarea].set(
                    H.div["error"](f"{type(exc).__name__}: {exc}")
                )
            else:
                if submitting:
                    page[actionarea].set("Saved")
                else:
                    page[actionarea].set(H.button("Update", name="update"))


class GUI:
    def __init__(self, page, db, queue, params, defaults):
        self.page = page
        self.db = db
        self.queue = queue
        self.params = defaults | params
        self.debounced = ClientWrap(queue, debounce=0.3, form=True)
        self.link_area = H.div["copy-link"](
            "📋 Copy link",
            H.span["copiable"](self.link()),
            __constructor={
                "module": Path(here / "lib.js"),
                "symbol": "clip",
                "arguments": [H.self()],
            },
        )

    def link(self):
        encoded = urlencode(
            {p: v for p, v in self.params.items() if "$" not in p and v}
        )
        return f"?{encoded}"

    async def loop(self, reset):
        gen = self.regen()
        done = False
        while True:
            if done:
                inp = await self.queue.get()
            else:
                try:
                    inp = await asyncio.wait_for(self.queue.get(), 0.01)
                except (asyncio.QueueEmpty, asyncio.exceptions.TimeoutError):
                    inp = None

            if inp is not None:
                self.params = inp
                new_gen = self.regen()
                if new_gen is not None:
                    done = False
                    gen = new_gen
                    self.page[self.link_area, ".copiable"].set(self.link())
                    reset()
                    continue

            try:
                element = next(gen)
            except StopIteration:
                done = True
                continue

            yield element

    def regen(self):
        yield from []


class SearchGUI(GUI):
    def __init__(self, page, db, queue, params, defaults):
        search_defaults = {
            "title": None,
            "author": None,
            "venue": None,
            "date-start": None,
            "date-end": None,
            "excerpt": None,
        }
        super().__init__(
            page=page,
            db=db,
            queue=queue,
            params=params,
            defaults=search_defaults | defaults,
        )

    def regen(self):
        results = search(
            title=self.params["title"],
            author=self.params["author"],
            venue=self.params["venue"],
            start=self.params["date-start"],
            end=self.params["date-end"],
            excerpt=self.params["excerpt"],
            allow_download=False,
            db=self.db,
        )
        try:
            yield from results
        except Exception as e:
            traceback.print_exception(e)

    def __hrepr__(self, H, hrepr):
        def _input(name, description, type="text"):
            return H.div["form-input"](
                H.label({"for": f"input-{name}"})(description),
                H.input(
                    name=name,
                    type=type,
                    oninput=self.debounced,
                    value=self.params.get(name, False) or False,
                ),
            )

        return H.form["search-form"](
            _input("title", "Title"),
            _input("author", "Author"),
            _input("venue", "Venue"),
            _input("excerpt", "Excerpt"),
            _input("date-start", "Start date", type="date"),
            _input("date-end", "End date", type="date"),
            self.link_area,
        )


async def regenerator(queue, regen, reset, db):
    gen = regen(db=db)
    done = False
    while True:
        if done:
            inp = await queue.get()
        else:
            try:
                inp = await asyncio.wait_for(queue.get(), 0.01)
            except (asyncio.QueueEmpty, asyncio.exceptions.TimeoutError):
                inp = None

        if inp is not None:
            new_gen = regen(inp, db)
            if new_gen is not None:
                done = False
                gen = new_gen
                reset()
                continue

        try:
            element = next(gen)
        except StopIteration:
            done = True
            continue

        yield element


def search_interface(event=None, db=None):
    def regen(event=None):
        title, author, venue, date_start, date_end, excerpt = (
            None,
            None,
            None,
            None,
            None,
            None,
        )
        if event is not None and event:
            if "title" in event.keys():
                title = event["title"]
            if (
                "value" in event.keys()
            ):  # If the name of the input (event key) is not specified, the default value will be the title
                title = event["value"]
            if "author" in event.keys():
                author = event["author"]
            if "venue" in event.keys():
                venue = event["venue"]
            if "date-start" in event.keys():
                date_start = event["date-start"]
            if "date-end" in event.keys():
                date_end = event["date-end"]
            if "excerpt" in event.keys():
                excerpt = event["excerpt"]

        results = search(
            title=title,
            author=author,
            venue=venue,
            start=date_start,
            end=date_end,
            excerpt=excerpt,
            allow_download=False,
            db=db,
        )
        try:
            yield from results
        except Exception as e:
            traceback.print_exception(e)

    return regen(event=event)


_config = None


def config():
    global _config
    if _config is None:
        _config = load_config(os.environ["PAPERONI_CONFIG"]).__enter__()
        config_var.set(_config)
    return _config


def template(path, location=None, **kw):
    location = location or path.parent
    return _template(
        path,
        _asset=lambda name: location / name,
        _embed=lambda name: template(
            location / name,
            location=location,
            **kw,
        ),
        **kw,
    )


# TODO: This is a copy of grizzlaxy.index.Index to avoid updating grizzlaxy during
# my time off -- OB
class Index(LoneBear):
    hidden = True

    def __init__(self, template=here / "mila-template.html"):
        super().__init__(self.run)
        self.location = template.parent if isinstance(template, Path) else None
        self.template = template

    async def run(self, request):
        scope = request.scope
        app = scope["app"]
        root_path = scope["root_path"]
        content = render("/", app.map, restrict=root_path)
        if content is None:
            content = render(
                "/", app.map, restrict="/".join(root_path.split("/")[:-1])
            )
        return template(
            self.template,
            body=H.div(content or "", id="index"),
            title="Application index",
        )


@keyword_decorator
def mila_template(fn, title=None, help=None):
    @wraps(fn)
    async def app(page):
        actual_title = getattr(fn, "__doc__", None) or title or ""
        actual_title = actual_title.removesuffix(".")
        page["head"].print(
            H.link(rel="stylesheet", href=here / "app-style.css")
        )
        page.print(
            template(
                here / "header.html",
                title=H.div(
                    actual_title,
                    " ",
                    H.a["ball"]("?", href=help) if help else "",
                ),
            )
        )
        page.print(target := H.div().autoid())
        return await fn(page, page[target])

    return app
