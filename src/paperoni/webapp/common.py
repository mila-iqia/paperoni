import asyncio
import traceback
from functools import wraps
from pathlib import Path
from urllib.parse import urlencode

from hrepr import H, J, returns
from starbear import ClientWrap, Queue, bear, template as _template
from starbear.components.editor import Editor
from starbear.core.app import LoneBear
from starbear.server.index import render

from ..cli_helper import search
from ..utils import keyword_decorator
from . import filters

here = Path(__file__).parent


class ContentEditor:
    def __init__(self, language, filter="", show_filter=False):
        self.language = language
        self.filter = filter
        self.show_filter = show_filter

    def read(self):
        return ""

    def change(self, new):
        return True

    def submit(self, new):
        raise NotImplementedError()

    async def __live__(self, element):
        q = Queue()
        if self.show_filter:
            element.print(
                H.div["editor-filter"](
                    "🔎",
                    H.input(
                        value=self.filter,
                        oninput=q.tag("filter").wrap(debounce=0.25),
                        autocomplete="off",
                    ),
                )
            )

        ed = Editor(
            value=self.read(),
            language=self.language,
            onChange=q.tag("edit"),
            bindings={"CtrlCmd+KeyS": q.tag("submit")},
        )
        element.print(
            H.div["config-editor"](
                H.div["editor"](ed),
                result := H.div["outcome"]("Saved").ensure_id(),
            )
        )

        async for event in q:
            try:
                if event.tag == "edit" and event["event"] == "change":
                    new = event["content"]
                    if self.change(new):
                        element[result].set(
                            H.button(
                                "Update", name="update", onclick=q.tag("submit")
                            )
                        )
                elif event.tag == "filter":
                    self.filter = event.value
                    await element[ed].js.editor.setValue(self.read())
                elif event.tag == "submit":
                    if self.submit(new):
                        element[result].set("Saved")
                else:
                    element.print(event)
            except Exception as exc:
                element[result].set(
                    H.div["error"](f"{type(exc).__name__}: {exc}")
                )


class ConfigEditor(ContentEditor):
    def __init__(self, file, language="javascript"):
        self.file = file

        # Don't ask. It's a mess.
        x = file
        while hasattr(x, "file"):
            x = x.file

        if x.suffix == ".yaml":
            language = "yaml"
        super().__init__(language)

    def read(self):
        return self.file.read()

    def change(self, new):
        self.file.write(new, dry=True)
        return True

    def submit(self, new):
        self.file.write(new, dry=False)
        return True


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
                autocomplete="off",
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


class SelectElement(SearchElement):
    def __init__(self, name, description, options, default=False):
        self.options = options
        super().__init__(
            name=name, description=description, default=default, type="select"
        )

    def element(self, queue):
        return H.div["form-input"](
            H.label({"for": f"input-{self.name}"})(self.description),
            H.select(
                [
                    H.option(
                        opt,
                        value=opt,
                        selected="selected" if opt == self.value else False,
                    )
                    for opt in self.options
                ],
                name=self.name,
                oninput=queue,
            ),
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


class BaseGUI:
    def __init__(
        self,
        elements,
        defaults={},
        params={},
        queue=None,
        button_label="Submit",
    ):
        self.button_label = button_label
        self.queue = queue or Queue()
        self.debounced = ClientWrap(self.queue, debounce=0.3, form=True)
        self.defaults = {}
        self.elements = {}
        self.add_elements(elements)
        self.defaults |= defaults
        self.params = self.defaults | params

    def add_elements(self, elements):
        for el in elements:
            self.elements[el.name] = el
            self.defaults[el.name] = el.default

    def link(self, page="", **extra):
        params = {**self.params, **extra}
        encoded = urlencode(
            {p: v for p, v in params.items() if "$" not in p and v}
        )
        return f"{page}?{encoded}"

    def form_footer(self):
        return H.button(self.button_label)

    def set_params(self, params):
        self.clear()
        self.params.update(params)

    def clear(self):
        self.params = {p: None for p in self.params.keys()}

    def form(self):
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
            H.div["search-extra"](self.form_footer()),
            onsubmit=self.debounced,
        )

    def __hrepr__(self, H, hrepr):
        return self.form()


class RegenGUI(BaseGUI):
    def __init__(
        self,
        elements,
        page,
        db,
        queue,
        params,
        defaults,
        first_batch_size=50,
        steady_batch_size=10,
    ):
        super().__init__(
            elements=elements,
            queue=queue,
            params=params,
            defaults=defaults,
            button_label=None,
        )
        self.first_batch_size = first_batch_size
        self.steady_batch_size = steady_batch_size
        self.page = page
        self.db = db
        self.wait_area = H.div["wait-area"](id=True)
        self.count_area = H.div["count-area"](
            H.span["shown"]("0"),
            " shown / ",
            H.span["count"]("0"),
            " found",
            id=True,
        )
        self.link_area = J(namespace=here / "lib.js").clip(
            returns(
                H.div["copy-link"](
                    "📋 Copy link", H.span["copiable"](self.link())
                )
            )
        )
        self.json_report_area = H.div["report-link"](id=True)
        self.csv_report_area = H.div["report-link"](id=True)

    async def loop(self, reset):
        def _soft_restart(new_gen):
            nonlocal batch_size, done, count, gen
            gen = new_gen
            done = False
            batch_size = self.first_batch_size
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
            self.page[self.count_area, ".count"].set("0")
            self.page[self.count_area, ".shown"].set("0")
            self.page[self.link_area, ".copiable"].set(self.link())
            self.page[self.wait_area].set(H.img(src=here / "three-dots.svg"))

        done = False
        batch_size = 0  # set by _soft_restart
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

            to_yield = []
            try:
                for _ in range(batch_size):
                    to_yield.append(next(gen))
            except StopIteration:
                done = True

            batch_size = self.steady_batch_size

            old_count = count
            count += len(to_yield)
            self.page[self.count_area, ".count"].set(str(count))

            diff = count - self.elements["limit"].value
            if diff > 0:
                # Throw away the excess
                to_yield = to_yield[:-diff]

            if to_yield:
                self.page[self.count_area, ".shown"].set(
                    str(old_count + len(to_yield))
                )

            if done:
                self.page[self.wait_area].set("✓")

            for x in to_yield:
                yield x

    def regen(self):
        yield from []


class SearchGUI(RegenGUI):
    def __init__(self, page, db, queue, params, defaults):
        elements = [
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
                name="affiliation",
                description="Affiliation",
                default=None,
            ),
            SearchElement(
                name="topic",
                description="Topic",
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
            FilterElement(
                name="peer-reviewed",
                description="Peer-reviewed",
                default=False,
                filter=filters.peer_reviewed,
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
        ]
        super().__init__(
            elements=elements,
            page=page,
            db=db,
            queue=queue,
            params=params,
            defaults=defaults,
        )

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
            self.page.error(message="An error occurred.", exception=e)
            traceback.print_exception(e)

    def form_footer(self):
        return [
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
        ]


def template(path, location=None, **kw):
    location = location or path.parent
    return _template(
        path,
        _asset=lambda name: location / name,
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
    actual_title = getattr(fn, "__doc__", None) or title or ""
    actual_title = actual_title.removesuffix(".")

    @wraps(fn)
    async def app(page):
        page.add_resources(here / "app-style.css")
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
        page.print(target := H.div(id=True))
        return await fn(page, page[target])

    return bear(app, template_params={"title": actual_title})
