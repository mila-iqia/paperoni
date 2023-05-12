import re
import subprocess
import sys
import unicodedata
from collections import defaultdict, deque
from functools import cached_property
from itertools import groupby
from typing import Generic, TypeVar

import bs4
from blessed import Terminal
from ovld import ovld
from pydantic import BaseModel as _BaseModel

T = TypeVar("T")
term = Terminal()


class BaseModel(_BaseModel):
    class Config:
        keep_untouched = (cached_property,)


class Word(BaseModel):
    text: str
    ymin: float
    ymax: float
    xmin: float
    xmax: float
    superscript: bool = False

    @cached_property
    def substantial(self):
        return len(self.text) >= 3


class Group(BaseModel, Generic[T]):
    parts: list[T]

    @cached_property
    def text(self):
        return " ".join(part.text for part in self.parts)

    @cached_property
    def ymin(self):
        return min(w.ymin for w in self.parts)

    @cached_property
    def ymax(self):
        return max(w.ymax for w in self.parts)

    @cached_property
    def xmin(self):
        return min(w.xmin for w in self.parts)

    @cached_property
    def xmax(self):
        return max(w.xmax for w in self.parts)

    def xoverlap(self, other):
        return overlap(
            min1=self.xmin, max1=self.xmax, min2=other.xmin, max2=other.xmax
        )

    def yoverlap(self, other):
        return overlap(
            min1=self.ymin, max1=self.ymax, min2=other.ymin, max2=other.ymax
        )


class Block(Group[Word]):
    @cached_property
    def base_min(self):
        try:
            return min(w.ymin for w in self.parts if w.substantial)
        except ValueError:
            return 0

    @cached_property
    def base_max(self):
        try:
            return max(w.ymax for w in self.parts if w.substantial)
        except ValueError:
            return 0

    @cached_property
    def base_height(self):
        return self.base_max - self.base_min


class Line(Group[Block]):
    pass


class Document(Group[Line]):
    pass


def coalesce(parts, initial_state, criterion):
    def _coalesce():
        if not q:
            return None

        elem = q.popleft()
        results = list(elem.parts)
        state = initial_state(elem)
        while q:
            elem = q[0]
            new_state = criterion(state, elem)
            if new_state:
                q.popleft()
                state = new_state
                results.extend(elem.parts)
            else:
                break
        return results

    if not parts:
        return []

    q = deque(parts)

    rval = []
    while q:
        new_parts = _coalesce()
        if new_parts is None:
            break
        rval.append(new_parts)

    return rval


def overlap(min1, max1, min2, max2):
    omin = max(min1, min2)
    omax = min(max1, max2)
    if omin >= omax:
        return False
    else:
        diff = omax - omin
        minheight = max(0.001, min(max2 - min2, max1 - min1))
        return (diff / minheight) > 0.5


def make_document_from_lines(lines):
    def _linear_init(elem):
        return elem.xmax

    def _linear_criterion(prev_xmax, elem):
        if 0 < elem.xmin - prev_xmax < 0.01:
            return elem.xmax
        else:
            return None

    def _similar_y_init(elem):
        return (elem.ymin, elem.ymax)

    def _similar_y_criterion(state, elem):
        ymin, ymax = state
        if overlap(elem.ymin, elem.ymax, ymin, ymax):
            ymin = min(elem.ymin, ymin)
            ymax = min(elem.ymax, ymax)
            return (ymin, ymax)
        else:
            return None

    # Remove large blocks
    lines = [line for line in lines if line.ymax - line.ymin < 0.05]

    # Reorder vertically
    lines.sort(key=lambda line: line.ymin)

    # Merge lines that are y-aligned
    lines = [
        Line(parts=sorted(parts, key=lambda block: block.xmin))
        for parts in coalesce(
            parts=lines,
            initial_state=_similar_y_init,
            criterion=_similar_y_criterion,
        )
    ]

    # Merge blocks inside lines that are close enough to their predecessors
    lines = [
        Line(
            parts=[
                Block(parts=new_parts)
                for new_parts in coalesce(
                    parts=line.parts,
                    initial_state=_linear_init,
                    criterion=_linear_criterion,
                )
            ]
        )
        for line in lines
    ]

    # Regroup the blocks into columns. Each "line" now corresponds to a
    # visually contiguous block in the document.
    lines = columnize(lines)

    doc = Document(parts=lines)

    # Mark superscripts
    mark_superscripts(doc)

    return doc


def columnize(lines):
    done_columns = []
    active_columns = []
    for line in lines:
        candidates = list(line.parts)
        previous_active = list(active_columns)
        active_columns.clear()
        for col in previous_active:
            candidates.sort(key=lambda block: block.xoverlap(col))
            if not candidates or not candidates[-1].xoverlap(col):
                done_columns.append(col)
                continue
            best = candidates.pop()
            if col.ymax - 0.01 < best.ymin < col.ymax + 0.01:
                active_columns.append(Line(parts=[*col.parts, best]))
            else:
                done_columns.append(col)
                active_columns.append(Line(parts=[best]))
        active_columns.extend(Line(parts=[block]) for block in candidates)

    return [*done_columns, *active_columns]


def make_document_from_layout(content):
    content = unicodedata.normalize("NFKC", content)
    soup = bs4.BeautifulSoup(content, "html.parser")
    lines = []
    for i, page in enumerate(soup.select("page")):
        h = float(page["height"])
        width = float(page["width"])
        lines += [
            Line(
                parts=[
                    Block(
                        parts=[
                            Word(
                                text=w.text,
                                ymin=float(w["ymin"]) / h + i,
                                ymax=float(w["ymax"]) / h + i,
                                xmin=float(w["xmin"]) / width,
                                xmax=float(w["xmax"]) / width,
                            )
                            for w in line.select("word")
                        ]
                    )
                ]
            )
            for line in page.select("line")
        ]
    return make_document_from_lines(lines)


#############################
# List text under some text #
#############################


@ovld
def undertext(grp: Group, text: str, extra_margin: int = 5, regexp=False):
    for part in grp.parts:
        yield from undertext(part, text, extra_margin, regexp)


@ovld
def undertext(line: Line, text: str, extra_margin: int = 5, regexp=False):
    if line.ymax >= 1:
        return
    for i, block in enumerate(line.parts[:-1]):

        def belongs():
            if regexp:
                return re.search(string=block.text, pattern=text)
            else:
                return text in block.text

        if len(block.text) < (len(text) + extra_margin) and belongs():
            break
    else:
        return
    yield [block.text for block in line.parts[i + 1 :]]


#####################
# Find superscripts #
#####################


class Superscript(BaseModel):
    superscript: str
    before: str
    after: str


@ovld
def mark_superscripts(x: Group):
    for part in x.parts:
        mark_superscripts(part)


@ovld
def mark_superscripts(x: Block):
    ymin = x.base_min
    ymax = x.base_max
    lh = x.base_height
    if lh > 20 or lh <= 0:
        return
    for word in x.parts:
        word.superscript = ((ymax - word.ymax) - (word.ymin - ymin)) / (
            lh
        ) >= 0.2


@ovld
def superscripts(x: Group):
    for part in x.parts:
        yield from superscripts(part)


@ovld
def superscripts(x: Line):
    if x.ymax >= 1:
        return

    parts = [("", False)]
    for block in x.parts:
        parts += [(w.text, w.superscript) for w in block.parts]
        parts.append(("", False))

    # Group by whether the word is superscript or not
    groups = [(k, list(g)) for k, g in groupby(parts, lambda x: x[1])]
    # Join the groups with spaces
    joined = [" ".join(w for w, _ in g if w) for k, g in groups]
    # Superscripts are at odd indices
    for i in range(1, len(joined), 2):
        yield Superscript(
            superscript=joined[i],
            before=joined[i - 1],
            after=joined[i + 1],
        )


def possible_superscripts(sup):
    if "," in sup:
        for entry in sup.split(","):
            yield from possible_superscripts(entry)
    yield sup
    if len(sup) > 1:
        for char in sup:
            if char.strip():
                yield char


def normalize(x):
    return unicodedata.normalize("NFKC", x).lower()


def classify_superscripts(doc):
    befores = defaultdict(list)
    afters = defaultdict(list)
    for ss in superscripts(doc):
        for sup in possible_superscripts(ss.superscript):
            if ss.before.strip():
                befores[sup].append(normalize(ss.before))
            if ss.after.strip():
                afters[sup].append(ss.after)
    results = defaultdict(set)
    for sup, possibilities in befores.items():
        for poss in possibilities:
            results[poss].update(afters[sup])
    return results


########################
# Display the document #
########################


@ovld
def display(x: Document):
    for line in x.parts:
        display(line)


@ovld
def display(x: Line):
    # print(x.ymin, end=" > ")
    for i, part in enumerate(x.parts):
        if i == 0:
            print(term.bold_orange(">"), end="")
        else:
            print(term.bold_yellow("|"), end="")
        display(part)
    print()


@ovld
def display(x: Block):
    for part in x.parts:
        display(part)


@ovld
def display(x: Word):
    if x.superscript:
        print(term.bold_cyan(x.text), end=" ")
    else:
        print(x.text, end=" ")


if __name__ == "__main__":
    try:
        pdf = sys.argv[1]
        subprocess.run(
            f"pdftotext -bbox-layout {pdf} __temporary.html", shell=True
        )
        content = open("__temporary.html").read()
        doc = make_document_from_layout(content)
        display(doc)

    except BrokenPipeError:
        pass
