"""TF5-37 and TF5-38: every number the docs set shows in prose carries its unit.

**The unit rule.** Prose is a page's text outside its fenced blocks. A number in prose is read
with the words beside it, and it carries its unit when one of these holds:

1. *The unit follows it.* The next word is a unit of ``UNITS`` ("56 minutes", "4 KB", "15.9
   points", "80% power"), or the number ends in ``%``, or it is hyphened to its unit ("a
   0.15-point drop").
2. *It counts the word that follows.* A whole number is followed by the plural it counts, at
   most two words on ("150 rows", "164 HumanEval problems", "49 more times"); ``1`` by the one
   thing ("1 repeat"). A number with decimals is never a count.
3. *The words before it name what it is.* One of ``NAMES`` stands within the five words
   before it, in its sentence, with only the words of ``LEADS``, other numbers and at most one
   other word between: "exit code 2", "Python 3.11", "temperature 0.7", "p = 0.036", "a score
   under 0.5", "mean faithfulness is 0.550", "the default is 100". A word in code, such as an
   option, names it with no other word between ("``--cut`` 0.5", "``--at`` below 0"), and a
   word of ``NUMBERED`` only from directly before ("line 3").
4. *It shares a neighbour's unit.* It is joined to a number that carries its unit, in the same
   sentence, at most four words off, by the words of ``CHAIN`` and at most two others ("9,158
   of 10,496 test cases", "107 rows of 150, then 87", "87.3%, then 86.8%", "from 1 to 100
   records"). A number with decimals shares only another's with decimals, or a share's.

**What the rule does not read**, each because it is no measure or is held elsewhere:

- counts, held by clause 2, and exit codes, held by clause 3;
- versions: a number of three parts, with any suffix (``0.1.0``, ``3.0.1.post1``); a version
  of two parts is named by clause 3 ("Python 3.11");
- ids and names that hold a digit (``#3``, ``HumanEval/129``, ``sha256``), dates
  (``2026-11-13``) and years;
- the number that numbers a heading or a list item ("## 2. Check the fix");
- whatever is written in code or quoted in double quotes: a literal value is written as code;
- a table's cells, which its column headings name;
- an indented block: a passage whose every line is indented four spaces or a tab, which
  Markdown renders as code, as the README's first screen writes its three commands; a line
  indented so inside a paragraph is still read;
- every fenced block: what a command printed is held by the blocks' own tests (TF5-14), and
  the blocks shown and not run are data.

The rule reads words, not grammar: a verb in ``-s`` after a whole number passes clause 2
("32 passes"). It is held on what it must catch by TF5-37's examples.

- TF5-37: the rule, by example: what carries its unit, each exception, and each way of
  dropping a unit that it catches.
- TF5-38: no page of the docs set, and no line of the CHANGELOG's entry for 0.1.0, shows a
  number in prose that carries no unit. (The CHANGELOG's pre-release entries are kept byte for
  byte, TF5-51, and are not read.)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from docs_support import CHANGELOG, expected_pages, passages, read, rel

UNITS = frozenset(
    "% percent point points minute minutes second seconds millisecond milliseconds ms hour hours day days week weeks "
    "kb mb gb byte bytes character characters column columns row rows line lines time times power".split()
)
JOINING = frozenset(
    "a an the and or but nor so yet if then than that which who whom whose what when where while as at by for from in into of on onto "
    "to with within without over under above below between against until through per is are was were be been being am do does did has "
    "have had it its this these those they them their he she we you i not no only also too still now here there apart later earlier "
    "ago long wide high deep old each every all both either neither out up down off about around across after before again once twice "
    "x × = — – -".split()
)
NAMES = frozenset(
    "exit exits exited exiting code codes python version versions temperature temperatures p alpha κ kappa seed seeds "
    "threshold thresholds score scores cut cuts ceiling floor mean means median ratio share shares rate rates default defaults limit "
    "level width height true false".split()
)
#: Words that name the number only when they stand directly before it: "line 3", "step 2".
NUMBERED = frozenset("line step page section".split())
LEADS = frozenset("of is are was were = under over below above outside inside at least most than to from as a an the between up exactly about around equal more less fewer not be by and or then".split())
CHAIN = frozenset("to and or of the those in then × x against from by through".split())

CODE, QUOTED = "⟦code⟧", "⟦quoted⟧"
PURE = re.compile(r"^(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")
SHARE = re.compile(r"^\d+(?:\.\d+)?%$")
NOT_READ = re.compile(
    r"""^(?:\d+\.\d+\.\d+[\w.]*           # a version of three parts, with any suffix
        |\d{4}-\d\d-\d\d                  # a date
        |\d+(?:\.\d+)?%                   # a share, with its sign
        |\d[\d,.]*-[A-Za-z][\w-]*         # a number hyphened to its unit
        |(?=.*\d).*[A-Za-zκ_/\#@=\\<>].*  # a name or an id that holds a digit
        )$""",
    re.X,
)
YEAR = re.compile(r"^(?:19|20)\d\d$")
WORD = re.compile(r"^[a-zA-Z][a-zA-Z-]*$")
STRIP = "()[]{},.;:!?\"'*_“”‘’…"


def _tokens(passage: str) -> tuple[list[str], list[bool]]:
    """The passage's words, code and quotations each written as one word, and for each word
    whether a sentence or a clause ends at it."""
    text = re.sub(r"`[^`]*`", f" {CODE} ", passage)
    text = re.sub(r"\]\([^)\s]*\)", "]", text)
    text = re.sub(r"\"[^\"\n]*\"|“[^”\n]*”", f" {QUOTED} ", text)
    words, ends = [], []
    for line in text.split("\n"):
        line = re.sub(r"^\s*(?:#+\s+)?(?:\d+\.\s+|[-*]\s+)?", "", line)
        for raw in line.split():
            core = raw.strip(STRIP)
            if core.endswith(("'s", "’s")):
                core = core[:-2]
            if core:
                words.append(core)
                ends.append(raw.rstrip("*_\"')]”’")[-1:] in tuple(".;:!?"))
    return words, ends


def bare_numbers(passage: str) -> list[tuple[str, str]]:
    """The numbers of a passage of prose that carry no unit under the unit rule, each with the
    words around it."""
    if all(line.lstrip().startswith("|") for line in passage.split("\n")):
        return []
    if all(re.match(r"^(?: {4,}|\t)", line) for line in passage.split("\n")):
        return []
    words, ends = _tokens(passage)
    read_ = [i for i, word in enumerate(words) if PURE.match(word) and not YEAR.match(word)]
    numeric = {i for i, word in enumerate(words) if PURE.match(word) or SHARE.match(word)}

    def after(i: int) -> bool:
        if ends[i]:
            return False
        whole, skipped = "." not in words[i], 0
        for j in range(i + 1, len(words)):
            word = words[j].lower()
            if word in UNITS:
                return True
            if not whole or not WORD.match(words[j]) or word in JOINING:
                return False
            if word.endswith("s") or words[i] == "1":
                return True
            if skipped == 2 or ends[j]:
                return False
            skipped += 1
        return False

    def before(i: int) -> bool:
        others = 0
        for j in range(i - 1, max(i - 6, -1), -1):
            word = words[j].lower()
            if ends[j]:
                return False
            if j == i - 1 and word in NUMBERED:
                return True
            if word in NAMES:
                return True
            if word == CODE:
                return others == 0
            if word not in LEADS and not PURE.match(words[j]) and not NOT_READ.match(words[j]):
                others += 1
                if others == 2 or not WORD.match(words[j]):
                    return False
        return False

    def shares(i: int, step: int, held: set[int]) -> bool:
        j, others = i + step, 0
        while 0 <= j < len(words) and abs(j - i) <= 4 and j not in numeric:
            if ends[j] or not (words[j].lower() in CHAIN or WORD.match(words[j])):
                return False
            others += words[j].lower() not in CHAIN
            j += step
        if not (0 <= j < len(words)) or abs(j - i) > 4 or others > 2 or j not in held or ends[i if step == 1 else j]:
            return False
        return "." not in words[i] or "." in words[j]

    held = {i for i in numeric if i not in read_} | {i for i in read_ if after(i) or before(i)}
    moved = True
    while moved:
        moved = False
        for i in read_:
            if i not in held and (shares(i, 1, held) or shares(i, -1, held)):
                held.add(i)
                moved = True
    return [(words[i], " ".join(words[max(0, i - 4):i + 5])) for i in read_ if i not in held]


def _release() -> str:
    text = read(CHANGELOG)
    head = re.search(r"(?m)^## 0\.1\.0 .*$", text)
    assert head is not None, "the CHANGELOG has no entry for 0.1.0"
    rest = text[head.end():]
    following = re.search(r"(?m)^## ", rest)
    return rest[:following.start()] if following else rest


# ---------- TF5-37 ----------

CARRIES = (
    "They are one agent run twice, 56 minutes apart.",
    "The file names its kind within its first 4 KB.",
    "It could have detected a drop of 15.9 points, and 10 was asked for.",
    "The ratio detectable at 80% power.",
    "A 0.15-point drop, in a design that could have detected more.",
    "On the same 150 rows of 146 questions.",
    "There are 164 HumanEval problems at two temperatures, 32 runs of each.",
    "The second missed 49 more times than the first.",
    "An import's summary says 1 repeat each.",
    "A wrong command line is exit code 2, and a refusal exits 1.",
    "It runs on Python 3.11 to 3.13 on macOS and Linux.",
    "It missed 12 times in 32, then 32 in 32, at temperature 0.7.",
    "The two runs do differ (p = 0.036).",
    "`--cut 0.5 --below` counts a score under 0.5 as missed.",
    "`--at` below 0 is refused.",
    "`--page-size N` asks for N records a request, from 1 to 100 (the default is 100).",
    "DeepEval reports 9,158 of 10,496 test cases passed, then 9,109 test cases: 87.3%, then 86.8%.",
    "It missed the cut less often: 107 rows of 150, then 87, on answer correctness.",
    "A mean of 0.453 over the 670 rows Ragas scored, against a mean of 0.458 over 1,800 rows.",
    "The window must be at least 80 columns by 24 rows.",
    "The title is on line 3, and step 2 imports.",
    "Over the rows that have a score, mean faithfulness is 0.550 for the base model.",
)
NOT_MEASURES = (
    "Tested on files written by DeepEval 4.2.6, and on evals 3.0.1.post1.",
    "HumanEval/129 missed, and so did #3; the digest is a sha256.",
    "Ruled on 2026-11-13. Poisson Labs, 2026.",
    "## 2. Check the fix",
    "1. Import both versions\n2. Check the fix",
    "A column pandas saved holds decimals, and its `1` is `1.0`; the summary says \"1 repeats each\".",
    "| code | meaning |\n|---|---|\n| 2 | the command line is wrong |",
    "    pip install poisson-trace\n    poisson-trace init\n    poisson-trace fix-check previous latest --inputs all --max-mde 0.2",
)
DROPPED = (
    ("They are one agent run twice, 56 apart.", ["56"]),
    ("The file names its kind within its first 4.", ["4"]),
    ("It could have detected a drop of 15.9, and 10 was asked for.", ["15.9", "10"]),
    ("On the same 150 of 146.", ["150", "146"]),
    ("DeepEval reports 9,158 of 10,496 passed, then 9,109.", ["9,158", "10,496", "9,109"]),
    ("A wrong command line is 2.", ["2"]),
    ("A number outside 0 to 1 is kept as it is.", ["0", "1"]),
    ("The two means do not show it: 0.453 over the 670 rows Ragas scored.", ["0.453"]),
    ("The window must be at least 80 × 24.", ["80", "24"]),
    ("The pull asks for the next 1,000 until it has them all.", ["1,000"]),
    ("A value that matched nothing shows as 0.", ["0"]),
    ("The rate fell. Then 87 were left.", ["87"]),
    ("It took 2.5 runs.", ["2.5"]),
    ("No string in `result.json` is longer than 400.", ["400"]),
    ("Mean faithfulness rose from 0.550 to 0.566.", ["0.550", "0.566"]),
    ("The search stops at depth 6.", ["6"]),
    ("The size the check is asked about is written after the flag:\n    0.2 is the one the examples use.", ["0.2"]),
)


@pytest.mark.parametrize("sentence", CARRIES)
def test_tf5_37_a_number_with_its_unit_passes(sentence: str) -> None:
    assert bare_numbers(sentence) == [], sentence


@pytest.mark.parametrize("sentence", NOT_MEASURES)
def test_tf5_37_what_the_rule_does_not_read(sentence: str) -> None:
    assert bare_numbers(sentence) == [], sentence


@pytest.mark.parametrize("sentence, bare", DROPPED, ids=[sentence for sentence, _ in DROPPED])
def test_tf5_37_a_number_that_drops_its_unit_is_caught(sentence: str, bare: list[str]) -> None:
    assert [number for number, _ in bare_numbers(sentence)] == bare, sentence


# ---------- TF5-38 ----------

PAGES = expected_pages()


@pytest.mark.parametrize("page", PAGES, ids=[rel(page) for page in PAGES])
def test_tf5_38_every_number_in_the_page_s_prose_carries_its_unit(page: Path) -> None:
    bare = [f"{rel(page)}:{line}: {number} in '{around}'" for line, passage in passages(read(page)) for number, around in bare_numbers(passage)]
    assert bare == [], "\n".join(bare)


def test_tf5_38_every_number_in_the_changelog_s_entry_carries_its_unit() -> None:
    bare = [f"CHANGELOG.md, 0.1.0, passage {line}: {number} in '{around}'" for line, passage in passages(_release()) for number, around in bare_numbers(passage)]
    assert bare == [], "\n".join(bare)
