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
from . import filters

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
        self.wait_area = H.div["wait-area"]().autoid()
        self.count_area = H.div["count-area"](
            H.span["count"]("0"), " found"
        ).autoid()
        self.link_area = H.div["copy-link"](
            "📋 Copy link",
            H.span["copiable"](self.link()),
            __constructor={
                "module": Path(here / "lib.js"),
                "symbol": "clip",
                "arguments": [H.self()],
            },
        )
        self.json_report_area = H.div["report-link"]().autoid()
        self.csv_report_area = H.div["report-link"]().autoid()

    def link(self, page="", **extra):
        params = {**self.params, **extra}
        encoded = urlencode(
            {p: v for p, v in params.items() if "$" not in p and v}
        )
        return f"{page}?{encoded}"

    async def loop(self, reset):
        def _soft_restart(new_gen):
            nonlocal done, count, gen
            gen = new_gen
            done = False
            count = 0
            self.page[self.json_report_area].set(
                H.a(
                    "JSON",
                    href=self.link(page="/report", limit=None, format="json"),
                )
            )
            self.page[self.csv_report_area].set(
                H.a(
                    "CSV",
                    href=self.link(page="/report", limit=None, format="csv"),
                )
            )
            self.page[self.link_area, ".copiable"].set(self.link())
            self.page[self.wait_area].set(H.img(src=here / "three-dots.svg"))

        gen = None
        _soft_restart(self.regen())

        while True:
            if done:
                inp = await self.queue.get()
            else:
                try:
                    inp = await asyncio.wait_for(self.queue.get(), 0.01)
                except (asyncio.QueueEmpty, asyncio.exceptions.TimeoutError):
                    inp = None

            if inp is not None:
                self.params = self.params | inp
                new_gen = self.regen()
                if new_gen is not None:
                    _soft_restart(new_gen)
                    reset()
                    continue

            try:
                self.page[self.count_area, ".count"].set(str(count))
                element = next(gen)
                count += 1
                if count > self.elements["limit"].value:
                    done = True
                    self.page[self.wait_area].set("~")
                    continue
            except StopIteration:
                done = True
                self.page[self.wait_area].set("✓")
                continue

            yield element

    def regen(self):
        yield from []


class SearchElement:
    def __init__(
        self,
        name,
        description,
        default=None,
        type="text",
        convert=None,
        hidden=False,
    ):
        self.name = name
        self.description = description
        self.default = self.value = default
        self.type = type
        self.convert = convert
        self.hidden = hidden

    def set_value(self, value):
        if self.convert is None:
            self.value = value
        else:
            self.value = self.convert(value)

    def update_keywords(self, kw):
        kw[self.name] = self.value

    def element(self, queue):
        return H.div["form-input"](
            H.label({"for": f"input-{self.name}"})(self.description),
            H.input(
                name=self.name,
                type=self.type,
                oninput=queue,
                value=self.value or False,
            ),
        )


class ExtraElement(SearchElement):
    def update_keywords(self, kw):
        pass

    def element(self, queue):
        return ""


class CheckboxElement(SearchElement):
    def __init__(self, name, description, default=False):
        super().__init__(
            name=name, description=description, default=default, type="checkbox"
        )

    def element(self, queue):
        return H.div["form-flag"](
            H.input(
                name=self.name,
                type="checkbox",
                oninput=queue,
                checked=self.value,
            ),
            H.label({"for": f"input-{self.name}"})(self.description),
        )


class FlagElement(CheckboxElement):
    def __init__(self, name, description, flag, default=False):
        super().__init__(name=name, description=description, default=default)
        self.flag = flag

    def set_value(self, value):
        self.value = bool(value)

    def update_keywords(self, kw):
        if self.value:
            flags = kw.setdefault("flags", [])
            flags.append(self.flag)


class FilterElement(CheckboxElement):
    def __init__(self, name, description, filter, default=False):
        super().__init__(name=name, description=description, default=default)
        self.filter = filter

    def set_value(self, value):
        self.value = bool(value)

    def update_keywords(self, kw):
        if self.value:
            filters = kw.setdefault("filters", [])
            filters.append(self.filter)


class RadioElement(SearchElement):
    def __init__(self, name, choices, default):
        super().__init__(name=name, description=None, default=default)
        self.choices = choices

    def set_value(self, value):
        self.value = value

    def update_keywords(self, kw):
        choice = self.choices[self.value]
        match choice["flag"]:
            case str(x):
                flags = kw.setdefault("flags", [])
                flags.append(x)
            case None:
                pass
            case x:
                filters = kw.setdefault("filters", [])
                filters.append(x)

    def element(self, queue):
        return H.div["form-radios"](
            H.label(
                H.input(
                    type="radio",
                    name=self.name,
                    value=value,
                    checked=value == self.value,
                    onchange=queue,
                ),
                choice["description"],
            )
            for value, choice in self.choices.items()
        )


class SearchGUI(GUI):
    def __init__(self, page, db, queue, params, defaults):
        self.elements = {}
        self.search_defaults = {}
        self.add_elements(
            SearchElement(
                name="title",
                description="Title",
                default=None,
            ),
            SearchElement(
                name="author",
                description="Author",
                default=None,
            ),
            SearchElement(
                name="venue",
                description="Venue",
                default=None,
            ),
            SearchElement(
                name="excerpt",
                description="Excerpt",
                default=None,
            ),
            SearchElement(
                name="start",
                description="Start date",
                default=None,
                type="date",
            ),
            SearchElement(
                name="end",
                description="End date",
                default=None,
                type="date",
            ),
            RadioElement(
                name="validation",
                choices={
                    "validated": {
                        "description": "Validated",
                        "flag": "validation",
                    },
                    "invalidated": {
                        "description": "Invalidated",
                        "flag": "!validation",
                    },
                    "not-processed": {
                        "description": "Not processed",
                        "flag": filters.no_validation_flag,
                    },
                    "all": {
                        "description": "All",
                        "flag": None,
                    },
                },
                default="all",
            ),
            ExtraElement(
                name="limit",
                description="Maximum number of results",
                default=1000,
                convert=int,
            ),
            SearchElement(
                name="sort",
                description="Sorting method",
                default="-date",
                hidden=True,
            ),
        )
        super().__init__(
            page=page,
            db=db,
            queue=queue,
            params=params,
            defaults=self.search_defaults | defaults,
        )

    def add_elements(self, *elements):
        for el in elements:
            self.elements[el.name] = el
            self.search_defaults[el.name] = el.default

    def regen(self):
        kw = {}
        for k, el in self.elements.items():
            if k in self.params:
                el.set_value(self.params[k])
                el.update_keywords(kw)
        results = search(**kw, allow_download=False, db=self.db)
        try:
            yield from results
        except Exception as e:
            traceback.print_exception(e)

    def __hrepr__(self, H, hrepr):
        for k, v in self.params.items():
            if k in self.elements:
                self.elements[k].set_value(v)
        inputs = [
            el.element(self.debounced)
            for el in self.elements.values()
            if not el.hidden
        ]
        return H.form["search-form"](
            H.div["main-inputs"](*inputs),
            H.div["search-extra"](
                self.wait_area,
                self.count_area,
                self.link_area,
                self.json_report_area,
                self.csv_report_area,
                H.button(
                    "Restart search",
                    name="restart",
                    onclick=self.queue.wrap(form=True),
                ),
            ),
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
