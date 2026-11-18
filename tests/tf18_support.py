"""Shared helpers for TF18's tests: the static pages and the HTML report (spec section 17.3 items
7, 8 and 9; section 11.7 as amended; section 11.8's ``to_html`` and ``build_pages``; the design's
section 3 and its rulings DM5 to DM14, all ruled yes on 2026-11-05; PA5, SB5 and SV15). This
pair's own readings are TF18-A1 on, ``log/trace-tf18-a/rulings.md``.

Not a test module and not collected.

The pages as these tests read them.

- **Where they are.** ``poisson-trace ui`` builds Trace's pages into
  ``<store>/.poisson/ui/trace/``, and nowhere else: ``index.html`` (the runs and the saved
  verdicts), one page per saved verdict of Trace's at ``<kind>/<id>.html`` (``where``,
  ``compare``, ``fix-check``, ``changes``; the id in full, 16 hex), one *could not say* page per
  saved verdict at ``<kind>/<id>/could-not-say.html``, and the fixed files ``style.css`` and
  ``ui.js``, Prove 0.1.3's bundle byte for byte (Prove's bundle holds the colour tokens inside
  ``style.css``; it has no third file). Nothing else (A1).
- **Every page** is Prove's page skeleton: ``<!doctype html>``, ``<html lang="en">``, the charset,
  Prove's Content-Security-Policy meta (:data:`PROVE_POLICY`), the viewport, a generator meta
  ``poisson-trace <version>``, the stylesheet and the script by relative path, the header (the
  tool, the view, the store's folder name), and Prove's footer with Trace's name and the page's
  address inside the UI: ``Built by poisson-trace from the store. Nothing was loaded from the
  network. Address: trace/<address>`` (A2).
- **A verdict page** (``<kind>/<id>.html``): its first ``<h1>`` is the verdict line,
  ``<verdict>␣␣<sentence>`` (section 11.7's check, which the amendment keeps; the mockup's title
  goes to ``<title>``, A3); ``<title>`` is the report's title line; then every line of the
  report as the plain command prints it, in order, under the report's own headings (DM14), with
  the continuous-measures section ``fix-check --measures`` prints where it prints it (A4). A
  condition cell may be written as its words (``task_id search · tool_fail_rate 0.55``) instead
  of its JSON, as the mockup does. The page links its could-not-say page and the runs page.
- **The where page** inlines the run's curve (``<figure id="curve">``) with its data as a table
  under it; **the compare page** inlines the two runs' curves (``<figure id="curves">``) and the
  hazard ratio with its range (``<figure id="hazard-ratio">``, DM8), each with its data as a
  table. The compare artifact carries both as ``charts/curves.svg`` and ``.json`` and
  ``charts/hazard-ratio.svg`` and ``.json`` (SV15, A9).
- **The index** opens with the verdict line ``runs`` prints for the store; one row per run with
  its number, name, id, target or tool, rows, failed, traces, started and status; a saved
  verdicts table, newest first, each row linking to its page; a link to each other store the
  config names (DM10) and, when Prove's own index is beside it, to ``../index.html`` (DM11).
- **No network.** Every ``href`` and ``src`` is a relative path that resolves to a file that is
  there, or a ``#`` anchor; no attribute holds a scheme but ``data:``.

The HTML report (``poisson-trace report DIR``) is the verdict page for the bundle's artifact,
self-contained: Prove's style inlined in one ``<style>``, the charts inline, no script, no
``<link>``, no ``href`` but ``#`` anchors, and the narrower policy :data:`REPORT_POLICY`. Section
11.7's checks hold on it, ``handover --check`` applies them, and ``to_html()`` is the same text.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from html.parser import HTMLParser
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

from conftest import FIXTURES
from tf0_support import REPO, Ran, chdir, trace, trace_import
from tf13_support import cli, workspace

TF18 = FIXTURES / "tf18"
PINS = TF18 / "main-pins.json"
MAIN = "4eb8c1b"
TOOL = "poisson-trace"
EV = ["--event", "violated", "--event", "timeout"]
KINDS = ("where", "compare", "fix-check", "changes")
BUNDLE = ("style.css", "ui.js")
# Prove 0.1.3's bundle as its wheel ships it (poisson_prove/_ui_bundle); a pin move shows here
BUNDLE_SHA256 = {
    "style.css": "6902e40411767403b52d469b6ae7c4affb4296aa2ba94d87ede61aff815ab043",
    "ui.js": "ca9a0195520b58fe64665deb3e6ff8cb0e04beddb8d1cf691872134b220c9ccc",
}
# Prove's Content-Security-Policy, every static page's (poisson_prove._render_ui.POLICY, 0.1.3)
PROVE_POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' "
    "data:; base-uri 'none'; form-action 'none'"
)
# the report's: inline style and images and nothing else (section 17.3 item 8; A6)
REPORT_POLICY = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'"
FOOTER = "Built by poisson-trace from the store. Nothing was loaded from the network. Address: {address}"
SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:")
# the look's four meanings, by value (docs/cli-look.md, the static UI's colour table): never in a chart
MEANING_COLOURS = ("#006300", "#5cc45c", "#8a5800", "#e5b23c", "#bf2626", "#f07070")
MEANING_CLASSES = ("w-ok", "w-warn", "w-bad", "var(--ok)", "var(--warn)", "var(--bad)")


def prove_bundle() -> dict[str, bytes]:
    folder = resources.files("poisson_prove") / "_ui_bundle"
    return {name: (folder / name).read_bytes() for name in BUNDLE}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def version() -> str:
    from importlib.metadata import version as v

    return v("poisson-trace")


# ---------- reading a page ----------

VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"})
BLOCKS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "dt", "dd", "tr", "figcaption", "pre", "caption", "summary", "blockquote"})
CELLS = frozenset({"td", "th"})


@dataclass
class Element:
    tag: str
    attrs: dict[str, str]
    parents: tuple[str, ...]
    text: str = ""
    index: int = 0


@dataclass
class Page:
    """A page as ``html.parser`` reads it: every element with its attributes and ancestors, its
    text, the leaf blocks of ``<main>`` in order, and whether the parser complained."""

    source: str
    elements: list[Element] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    block_tags: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def all(self, tag: str) -> list[Element]:
        return [e for e in self.elements if e.tag == tag]

    def first(self, tag: str) -> Element | None:
        found = self.all(tag)
        return found[0] if found else None

    def text_of(self, tag: str) -> str | None:
        e = self.first(tag)
        return None if e is None else e.text

    @property
    def h1(self) -> str | None:
        return self.text_of("h1")

    @property
    def title(self) -> str | None:
        return self.text_of("title")

    def meta(self, **match: str) -> list[str]:
        out = []
        for e in self.all("meta"):
            if all(e.attrs.get(k.replace("_", "-")) == v for k, v in match.items()):
                out.append(e.attrs.get("content", ""))
        return out

    @property
    def policy(self) -> list[str]:
        return self.meta(http_equiv="Content-Security-Policy")

    @property
    def generator(self) -> list[str]:
        return self.meta(name="generator")

    @property
    def footer(self) -> str | None:
        e = self.first("footer")
        return None if e is None else norm(e.text)

    def headings(self) -> list[str]:
        return [b for b, t in zip(self.blocks, self.block_tags, strict=True) if t in ("h2", "h3")]

    def hrefs(self) -> list[str]:
        return [e.attrs["href"] for e in self.elements if "href" in e.attrs]

    def srcs(self) -> list[str]:
        return [e.attrs["src"] for e in self.elements if "src" in e.attrs]

    def by_id(self, ident: str) -> Element | None:
        return next((e for e in self.elements if e.attrs.get("id") == ident), None)

    def inside(self, ident: str) -> Page:
        """The page cut to the element with this id: its source between its tags, read again."""
        start = re.search(rf'<(\w+)[^>]*\bid="{re.escape(ident)}"', self.source)
        assert start is not None, ident
        tag = start.group(1)
        depth, at = 0, start.start()
        for m in re.finditer(rf"<(/?){tag}\b[^>]*>", self.source[at:]):
            depth += -1 if m.group(1) else 1
            if depth == 0:
                return read(self.source[at:at + m.end()], fragment=True)
        raise AssertionError(f"#{ident} is never closed")


class _Reader(HTMLParser):
    def __init__(self, page: Page) -> None:
        super().__init__(convert_charrefs=True)
        self.page = page
        self.stack: list[Element] = []
        self.texts: list[list[str]] = []  # per open element, its text
        self.buffers: list[tuple[str, list[str]]] = []  # leaf blocks inside main
        self.in_main = 0
        self.in_svg = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        e = Element(tag, {k: (v or "") for k, v in attrs}, tuple(x.tag for x in self.stack), index=len(self.page.elements))
        self.page.elements.append(e)
        if tag == "main":
            self.in_main += 1
        if tag == "svg":
            self.in_svg += 1
        if self.in_main and not self.in_svg:
            if tag in BLOCKS:
                self.buffers.append((tag, []))
            elif tag in CELLS and self.buffers and self.buffers[-1][0] == "tr" and self.buffers[-1][1]:
                self.buffers[-1][1].append(" | ")
        if tag in VOID:
            return
        self.stack.append(e)
        self.texts.append([])

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        e = Element(tag, {k: (v or "") for k, v in attrs}, tuple(x.tag for x in self.stack), index=len(self.page.elements))
        self.page.elements.append(e)

    def handle_endtag(self, tag: str) -> None:
        if self.in_main and not self.in_svg and tag in BLOCKS and self.buffers and self.buffers[-1][0] == tag:
            kind, parts = self.buffers.pop()
            text = norm("".join(parts))
            if text:
                self.page.blocks.append(text)
                self.page.block_tags.append(kind)
        if tag == "svg" and self.in_svg:
            self.in_svg -= 1
        if tag == "main" and self.in_main:
            self.in_main -= 1
        if tag in VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i].tag == tag:
                while len(self.stack) > i:
                    done = self.stack.pop()
                    done.text = "".join(self.texts.pop())
                    if self.texts:
                        self.texts[-1].append(done.text)
                return
        self.page.errors.append(f"an end tag with no start: </{tag}>")

    def handle_data(self, data: str) -> None:
        if self.texts:
            self.texts[-1].append(data)
        if self.in_main and not self.in_svg and self.buffers:
            self.buffers[-1][1].append(data)

    def error(self, message: str) -> None:  # pragma: no cover - never called on Python 3.10 and later
        self.page.errors.append(message)


def read(text: str, fragment: bool = False) -> Page:
    """A page read; a fragment of one (``Page.inside``) is read as if it stood in ``<main>``."""
    page = Page(text)
    reader = _Reader(page)
    reader.in_main = 1 if fragment else 0
    reader.feed(text)
    reader.close()
    while reader.stack:
        done = reader.stack.pop()
        done.text = "".join(reader.texts.pop())
        if done.tag not in ("html", "body", "head", "p", "li", "dt", "dd", "tr", "td", "th", "tbody", "thead", "option"):
            page.errors.append(f"never closed: <{done.tag}>")
    return page


def read_file(path: Path) -> Page:
    return read(path.read_text(encoding="utf-8"))


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# ---------- a page's references ----------


def references(page: Page) -> list[tuple[str, str, str]]:
    """Every attribute that names something to load or open: ``(tag, attribute, value)``."""
    out = []
    for e in page.elements:
        for name in ("href", "src", "action", "data", "poster", "srcset", "xlink:href", "formaction", "background"):
            if name in e.attrs:
                out.append((e.tag, name, e.attrs[name]))
    return out


def resolve(page_path: Path, ref: str) -> Path | None:
    """Where a relative reference on the page at ``page_path`` points, its anchor dropped; None
    for an anchor of the page itself."""
    parts = urlsplit(ref)
    if parts.scheme or parts.netloc or ref.startswith("//"):
        raise AssertionError(f"not a relative path: {ref}")
    if not parts.path:
        return None
    target = page_path.parent
    for piece in PurePosixPath(unquote(parts.path)).parts:
        target = target.parent if piece == ".." else target / piece
    return target


# ---------- the store and its pages ----------


def ui_root(store: Path) -> Path:
    return store / ".poisson" / "ui"


def pages_of(store: Path) -> Path:
    return ui_root(store) / "trace"


def artifacts(store: Path) -> dict[str, list[str]]:
    """Trace's saved verdicts in a store, by kind: their ids."""
    base = store / ".poisson" / "artifacts"
    out: dict[str, list[str]] = {}
    for kind in KINDS:
        folder = base / kind
        out[kind] = sorted(p.name for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []
    return out


def artifact_folder(store: Path, kind: str, ident: str) -> Path:
    return store / ".poisson" / "artifacts" / kind / ident


def expected_files(store: Path) -> set[str]:
    """The files of a store's pages (A1): the index, the fixed files, a page and a could-not-say
    page per saved verdict of Trace's."""
    out = {"index.html", *BUNDLE}
    for kind, ids in artifacts(store).items():
        for ident in ids:
            out |= {f"{kind}/{ident}.html", f"{kind}/{ident}/could-not-say.html"}
    return out


def files_under(folder: Path) -> set[str]:
    return {str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file()}


def snapshot(folder: Path, skip: str | None = None) -> dict[str, str]:
    """Every file under a folder and its digest, the folder ``skip`` names left out."""
    out = {}
    if not folder.is_dir():
        return out
    for p in sorted(folder.rglob("*")):
        rel = str(p.relative_to(folder))
        if skip is not None and (rel == skip or rel.startswith(skip + "/")):
            continue
        if p.is_file():
            out[rel] = sha256(p.read_bytes())
    return out


# ---------- the pages workspace ----------

# Each verdict the pages workspace saves: (store, argv without --save). The Prove store's are the
# design session's own (the mockups' ids); the table store's hold tries with no outcome.
SAVES: dict[str, tuple[str, list[str]]] = {
    "where after": ("store", ["where", "agent after", "--store", "store", *EV]),
    "where before": ("store", ["where", "agent before", "--store", "store", *EV]),
    "compare": ("store", ["compare", "agent before", "agent after", "--store", "store", *EV, "--max-mde-hr", "1.5"]),
    "fix-check": ("store", ["fix-check", "agent before", "agent after", "--store", "store", *EV, "--inputs", "all", "--max-mde", "0.1"]),
    "changes": ("store", ["changes", "agent before", "agent after", "--store", "store", *EV]),
    "fix-check tables": ("tables", ["fix-check", "old", "new", "--store", "tables", "--event", "missed", "--inputs", "all", "--max-mde", "0.5"]),
    "changes tables": ("tables", ["changes", "old", "new", "--store", "tables", "--event", "missed"]),
}
# the mockups' ids, read off the design's pages (log/trace-design/pages/)
MOCKUP_IDS = {"where after": "13c7d6008e73d824", "where before": "a69a60ecfbd40931", "compare": "004ef6df2b56cae9",
              "fix-check": "2ef6dc12196c5aa9"}


def build_work(tmp: Path) -> Path:
    """TF13's workspace (``tf13_support.workspace``) with every verdict of :data:`SAVES` saved:
    the Prove store holds two where verdicts, a compare, a fix-check and a changes, and Prove's
    own saved comparison that came with the fixture; the table store a fix-check and a changes.
    ``conf/trace.toml`` names both stores. No store has pages yet. Where each verdict was saved
    is kept in ``ids.json`` beside them (:func:`id_of`)."""
    work = workspace(tmp)
    ids: dict[str, list[str]] = {}
    for label, (store, argv) in SAVES.items():
        ran = cli(work, [*argv, "--save", "--json"])
        assert ran.code == 0, (label, ran.text)
        kind, ident = json.loads(ran.out)["saved"].split("/")[-2:]
        ids[label] = [store, kind, ident]
    (work / "ids.json").write_text(json.dumps(ids), encoding="utf-8")
    # a save builds the pages (A7); the workspace starts with none, as a store does
    for store in ("store", "tables"):
        shutil.rmtree(ui_root(work / store), ignore_errors=True)
    return work


def copy_work(src: Path, tmp: Path, name: str = "work") -> Path:
    dest = tmp / name
    shutil.copytree(src, dest, symlinks=True)
    return dest


def ui(work: Path, *argv: str) -> Ran:
    return cli(work, ["ui", *argv])


def id_of(work: Path, label: str) -> tuple[str, str, str]:
    """``(store, kind, id)`` of a verdict of :data:`SAVES`, as its ``--save --json`` gave it."""
    store, kind, ident = json.loads((work / "ids.json").read_text(encoding="utf-8"))[label]
    return store, kind, ident


# ---------- what a verdict page shows ----------


def measures_argv(argv: Sequence[str]) -> list[str]:
    return [*argv, "--measures"] if argv[0] == "fix-check" else list(argv)


def report_lines(text: str) -> list[str]:
    """The lines a verdict page shows of a plain report in its ``<main>``: everything after the
    title line (which is the page's ``<title>``), leaving out the ``next:`` line; blank lines and
    markdown rule rows dropped."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("# "))
    body = [line for line in lines[start + 1:] if line.strip() and not line.startswith("next: ")]
    return [line for line in body if not re.fullmatch(r"\|(?:-+\|)+", line.strip())]


def title_line(text: str) -> str:
    return next(line for line in text.splitlines() if line.startswith("# "))[2:]


def _strip_inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    return text


def condition_words(cell: str) -> str | None:
    """A condition written as JSON, as the pages may write it: ``key value · key value``."""
    try:
        value = json.loads(cell)
    except ValueError:
        return None
    if not isinstance(value, dict):
        return None
    return " · ".join(f"{k} {v if isinstance(v, str) else json.dumps(v)}" for k, v in value.items())


def line_forms(line: str) -> list[str]:
    """The forms a report line may take on a page, whitespace collapsed: a heading's text, a list
    item's text, a table row's cells joined by `` | `` (its first cell as JSON or as words), a
    paragraph's text; markdown's bold and code marks dropped."""
    if line.startswith("## ") or line.startswith("### "):
        return [norm(line.split(" ", 1)[1])]
    if line.startswith("|"):
        cells = [_strip_inline(c.strip()) for c in line.strip().strip("|").split("|")]
        forms = [" | ".join(cells)]
        words = condition_words(cells[0])
        if words is not None:
            forms.append(" | ".join([words, *cells[1:]]))
        return [norm(f) for f in forms]
    if line.startswith("- "):
        return [norm(_strip_inline(line[2:]))]
    return [norm(_strip_inline(line))]


def missing_lines(page: Page, lines: Sequence[str]) -> list[str]:
    """The report lines the page does not show, in order: each must be a block of ``<main>`` at or
    after the previous one's, or a ``<dt>`` and the ``<dd>`` after it read as ``label: text``."""
    blocks = page.blocks
    at = 0
    missing = []
    for line in lines:
        forms = line_forms(line)
        found = None
        for i in range(at, len(blocks)):
            if blocks[i] in forms:
                found = i
                break
            if page.block_tags[i] == "dt" and i + 1 < len(blocks) and f"{blocks[i]}: {blocks[i + 1]}" in forms:
                found = i + 1
                break
        if found is None:
            missing.append(line)
        else:
            at = found + 1
    return missing


def verdict_line(doc: dict[str, Any]) -> str:
    return f"{doc['verdict']}  {doc['sentence']}"


# ---------- the HTML report and its checks ----------

FORBIDDEN = ("script", "link", "iframe", "object", "embed")


def section_11_7(page: Page, result: dict[str, Any]) -> list[str]:
    """Section 11.7's checks, as ``handover --check`` applies them, and what fails."""
    fails = list(page.errors)
    fails += [f"<{t}>" for t in FORBIDDEN if page.all(t)]
    for e in page.elements:
        for k, v in e.attrs.items():
            if SCHEME.match(v):
                fails.append(f"{e.tag} {k}={v}")
    if page.h1 != verdict_line(result):
        fails.append(f"h1 {page.h1!r}")
    return fails


def redigest(bundle: Path, name: str) -> None:
    """``handover.json``'s entry for a file made to agree with the file as it now is: what a
    bundle someone edited by hand and re-listed looks like."""
    doc = json.loads((bundle / "handover.json").read_text(encoding="utf-8"))
    data = (bundle / name).read_bytes()
    for entry in doc["files"]:
        if entry["name"] == name:
            entry["sha256"] = sha256(data)
            entry["bytes"] = len(data)
    (bundle / "handover.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


# ---------- the browser ----------


def recording_browser(tmp: Path) -> tuple[dict[str, str], Path]:
    """An environment whose ``BROWSER`` is a script that writes the address it was given to a
    file, and that file: ``webbrowser`` runs it in place of a browser."""
    log = tmp / "opened.txt"
    script = tmp / "browser.py"
    script.write_text(
        "import sys\nfrom pathlib import Path\n"
        f"p = Path({str(log)!r})\n"
        "p.write_text((p.read_text() if p.exists() else '') + sys.argv[1] + '\\n')\n",
        encoding="utf-8",
    )
    import sys

    return {"BROWSER": f"{sys.executable} {script} %s"}, log


# ---------- what must not move: the pins of main ----------


def pin_corpus() -> dict[str, tuple[str, str, list[list[str]]]]:
    """Every invocation whose plain and ``--json`` output TF18 leaves as main prints it, piped:
    label to (where it runs, the command, its steps). The failure breakdown pair's corpus whole
    (``breakdown_support.piped_corpus``: TF13-32's and TF6-1's), and beside it every verb's help,
    the commands that save (``--save``, ``--out``, ``--svg``) and ``handover``. A step
    ``["!edit", FILE]`` appends a byte to FILE (a bundle made invalid)."""
    from breakdown_support import piped_corpus

    out = dict(piped_corpus())
    # the import's help lists the readers, so it moves with each reader pair, which holds it (for
    # LangSmith, test_tf24_unchanged.py)
    for verb in ("init", "runs", "name", "where", "compare", "fix-check", "changes", "handover", "doctor"):
        out[f"help: {verb}"] = ("work", "trace", [[verb, "--help"]])
    for label, (_store, argv) in SAVES.items():
        out[f"save: {label}"] = ("work", "trace", [[*argv, "--save"], [*argv, "--save", "--json"], [*argv, "--save"]])
    fix = SAVES["fix-check"][1]
    for label in ("where after", "compare", "fix-check", "changes"):
        argv = SAVES[label][1]
        out[f"out: {label}"] = ("work", "trace", [[*argv, "--out", "b1"], [*argv, "--out", "b1"],
                                                  [*argv, "--out", "b1", "--force", "--json"]])
    out["svg: where"] = ("work", "trace", [[*SAVES["where after"][1], "--svg", "c.svg"], [*SAVES["where after"][1], "--svg", "c.svg", "--json", "--force"]])
    out["handover: not valid"] = ("work", "trace", [[*fix, "--out", "hb"], ["!edit", "hb/result.json"], ["handover", "--check", "hb"]])
    out["handover: no folder"] = ("work", "trace", [["handover", "--check", "no-such"]])
    out["handover: not a bundle"] = ("work", "trace", [["handover", "--check", "conf"]])
    out["handover: no check"] = ("work", "trace", [["handover"]])
    return out


#: The invocations whose output TF18 changes, pinned from main to say exactly how: the top help
#: gains the two verbs (A10); the line naming the verbs gains them (A11); ``handover --check`` on
#: a valid bundle gains its ``next:`` line (SB5, A12).
CHANGED: dict[str, tuple[str, str, list[list[str]]]] = {
    "help: top": ("work", "trace", [["--help"]]),
    "verb: unknown": ("work", "trace", [["nosuch"]]),
    "verb: none": ("work", "trace", [[]]),
    "handover: ok": ("work", "trace", [[*SAVES["fix-check"][1], "--out", "hb"], ["handover", "--check", "hb"]]),
}

#: The slow ones: the larger fixtures and the DeepEval import, as the breakdown pair has them.
SLOW = frozenset({"import: deepeval", "import json: deepeval", "fixture: where cs", "fixture: compare tau2", "fixture: fix-check tau2",
                  "fixture: fix-check tau2 all", "fixture: fix-check humaneval", "fixture: changes humaneval"})


def normal(text: str, *roots: Path) -> str:
    from pin_support import as_pinned

    for root in roots:
        text = text.replace(str(root.resolve()), "<ROOT>").replace(str(root), "<ROOT>")
    # Prove's version, where Trace prints it, is written as the pins hold it (pin_support.as_pinned; ruled 2026-11-17, PV-5)
    return as_pinned(text)


def run_steps(work: Path, place: str, kind: str, steps: Sequence[Sequence[str]]) -> Iterator[Ran]:
    """Each step of a corpus case, run where the case says, its result yielded."""
    from tf13_support import cli_import

    for step in steps:
        if step and step[0] == "!edit":
            with (work / step[1]).open("ab") as f:
                f.write(b" ")
            continue
        if place == "work":
            yield (cli if kind == "trace" else cli_import)(work, list(step))
        else:
            with chdir(REPO):
                yield trace(list(step)) if kind == "trace" else trace_import(list(step))


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
