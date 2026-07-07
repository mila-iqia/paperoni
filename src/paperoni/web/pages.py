"""
FastAPI routes for serving markdown-based pages.

Every ``*.md`` file found under the package's own ``assets`` directory and
under ``config.server.assets`` (if set) is served at a URL mirroring its path
relative to whichever assets root it comes from. Files in
``config.server.assets`` take precedence over the package's built-in pages
with the same mount path.

A file named ``index.md`` is special-cased to be served at ``/`` instead of
``/index``.

A file named ``name--lang.md`` (e.g. ``help--fr.md``) is a localization of
``name.md``. Only ``fr`` is supported at the moment. The double dash lets
base filenames contain single dashes (e.g. ``mila-instructions.md``) without
being mistaken for a localization.

A ``<!-- capability: xxx -->`` comment in the english-lang markdown file
gates the page behind that capability.
"""

import re
from pathlib import Path

import markdown
from fastapi import Depends, FastAPI, HTTPException, Request

from ..config import config
from .helpers import render_template

here = Path(__file__).parent

_MD_EXTENSIONS = ["extra", "codehilite", "toc", "attr_list"]

# Languages recognized in `name--lang.md` localization files.
_LANGUAGES = ("fr",)
_LOCALIZED_NAME_RE = re.compile(rf"^(?P<base>.+)--(?P<lang>{'|'.join(_LANGUAGES)})$")

# A `<!-- capability: xxx -->` comment declares the capability required to view a page.
_CAPABILITY_RE = re.compile(r"<!--\s*capability:\s*(?P<capability>[\w-]+)\s*-->\n?")


def _split_locale(relative_stem: str) -> tuple[str, str]:
    """Split a file's path (relative to an assets root, without .md) into (base_stem, lang)."""
    parent, _, name = relative_stem.rpartition("/")
    match = _LOCALIZED_NAME_RE.match(name)
    if not match:
        return relative_stem, "en"

    base_name = match.group("base")
    base_stem = f"{parent}/{base_name}" if parent else base_name
    return base_stem, match.group("lang")


def _mount_path(base_stem: str) -> str:
    """Turn a markdown file's base stem into the URL it should be served at.

    `index.md` is the index of its directory, so e.g. `xxx/index.md` mounts
    at `/xxx/` (and top-level `index.md` mounts at `/`).
    """
    parent, _, name = base_stem.rpartition("/")
    if name == "index":
        return f"/{parent}/" if parent else "/"
    return f"/{base_stem}"


def _iter_markdown_files(root: Path | None):
    """Yield (mount_path, lang, path) for every markdown file under root."""
    if not root or not root.exists():
        return

    for path in sorted(root.rglob("*.md")):
        relative_stem = path.relative_to(root).with_suffix("").as_posix()
        base_stem, lang = _split_locale(relative_stem)
        yield _mount_path(base_stem), lang, path


def _build_page_index() -> dict[str, dict[str, Path]]:
    """Build a {mount_path: {lang: path}} index, custom assets overriding package assets."""
    pages: dict[str, dict[str, Path]] = {}

    custom_root = Path(config.server.assets) if config.server.assets else None
    for root in (here / "assets", custom_root):
        for mount, lang, path in _iter_markdown_files(root):
            pages.setdefault(mount, {})[lang] = path

    return pages


def _render_markdown_page(mount: str, files: dict[str, Path], request: Request):
    en_path = files.get("en")
    if en_path is None:
        raise HTTPException(status_code=404, detail="Page not found")

    en_text = _CAPABILITY_RE.sub("", en_path.read_text(encoding="utf-8"), count=1)
    content_en = markdown.markdown(en_text, extensions=_MD_EXTENSIONS)

    fr_path = files.get("fr")
    content_fr = (
        markdown.markdown(fr_path.read_text(encoding="utf-8"), extensions=_MD_EXTENSIONS)
        if fr_path
        else None
    )

    if mount == "/":
        page_title = "Home"
    else:
        name = mount.rstrip("/").rsplit("/", 1)[-1]
        page_title = name.replace("-", " ").replace("_", " ").title()

    return render_template(
        "markdown.html",
        request,
        help_section=False,
        page_title=page_title,
        content_en=content_en,
        content_fr=content_fr,
    )


def install_pages(app: FastAPI) -> FastAPI:
    """Install a route for every markdown page found in the assets directories."""
    hascap = app.auth.get_email_capability

    for mount, files in _build_page_index().items():
        if "en" not in files:
            continue

        capability_match = _CAPABILITY_RE.search(files["en"].read_text(encoding="utf-8"))
        capability = capability_match.group("capability") if capability_match else None
        dependencies = [Depends(hascap(capability, redirect=True))] if capability else []

        def make_handler(mount=mount, files=files):
            async def handler(request: Request):
                return _render_markdown_page(mount, files, request)

            return handler

        app.add_api_route(
            mount,
            make_handler(),
            methods=["GET"],
            dependencies=dependencies,
            include_in_schema=False,
        )

    return app
