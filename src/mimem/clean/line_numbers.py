"""Strip the line numbers that journals add to manuscripts under review.

A double-spaced submission or preprint often carries a number beside every line. PDF extraction
puts those numbers *into the text stream*, on their own line, which does two kinds of damage:

* a hyphenated word breaks around one -- ``recov-\\n19\\nery`` -- so dehyphenation sees
  ``recov-`` followed by ``19``, keeps the hyphen (the continuation is a digit) and produces
  ``recov-19 ery``. The word is destroyed and a number is spoken in the middle of it;
* every other number lands mid-sentence, where it is read aloud as if it meant something.

This has to run before :mod:`mimem.clean.dehyphenate`, which flattens the line structure the
detection depends on.

Detection is by *sequence*, not by pattern: a lone integer on a line proves nothing, but a few
hundred of them climbing monotonically through the document is line numbering and nothing else.
That is what keeps table cells, equation numbers and stray figures safe.
"""

from __future__ import annotations

import re
from itertools import pairwise
from statistics import median

from mimem.ir import Block, BlockKind, DiagnosticLevel, Document

#: A line holding nothing but an integer.
LINE_NUMBER_RE = re.compile(r"^\s*(\d{1,4})\s*$")

#: Below this many candidates, there is no sequence to speak of and we leave the document alone.
MIN_CANDIDATES = 20

#: Fraction of adjacent candidate pairs that must increase for this to be a numbering sequence.
MIN_INCREASING = 0.70

#: Line numbers step by a small constant (usually 1, or 5 when only every fifth line is marked).
MAX_MEDIAN_STEP = 5

#: Fraction of *all* lines in the document that must be lone integers.
#:
#: This is the test that separates real line numbering from things that merely look monotonic.
#: A published paper carries a handful of lone integers -- affiliation superscripts on their own
#: line, the journal's continuous folio numbers -- and on a Springer article those two sequences
#: interleave into something that passes the monotonic test comfortably (1..9 for affiliations,
#: then 7478..7499 for pages). Line numbering is different in kind: it marks roughly every line,
#: so it is dense, and density is what we require.
MIN_LINE_FRACTION = 0.10

#: Fraction of the integers between the smallest and largest candidate that must actually occur.
#:
#: Line numbering is contiguous: 1, 2, 3, ... (or 1..50 restarting each page), so it covers its
#: own range almost completely. The Springer false positive was two short runs far apart --
#: affiliation markers 1..9 and folio numbers 7478..7499 -- which is 31 values spread over a
#: range of 7499, and no amount of monotonicity makes that line numbering.
MIN_RANGE_COVERAGE = 0.50

#: Blocks whose internal numbers may legitimately look like a sequence.
#:
#: Note the ordering: this stage runs first, before :mod:`mimem.clean.sections` retypes
#: reference entries, so in practice only TABLE and CODE are ever matched here. REFERENCE is
#: listed because the guard should still hold if this is ever called on a document that has
#: already been through section assignment.
_SKIP_KINDS = frozenset({BlockKind.TABLE, BlockKind.CODE, BlockKind.REFERENCE})


def _candidates(doc: Document) -> list[tuple[Block, int, int]]:
    out: list[tuple[Block, int, int]] = []
    for block in doc.blocks:
        if block.kind in _SKIP_KINDS or "\n" not in block.text:
            continue
        for i, line in enumerate(block.text.split("\n")):
            m = LINE_NUMBER_RE.match(line)
            if m:
                out.append((block, i, int(m.group(1))))
    return out


def _total_lines(doc: Document) -> int:
    return sum(block.text.count("\n") + 1 for block in doc.blocks if block.text)


def looks_like_line_numbering(values: list[int], total_lines: int) -> bool:
    """Is this list of lone integers a line-numbering sequence?

    Four tests, all required: enough of them, dense enough relative to the document, covering
    their own numeric range, and climbing in small steps.
    """
    if len(values) < MIN_CANDIDATES:
        return False
    if total_lines <= 0 or len(values) / total_lines < MIN_LINE_FRACTION:
        return False
    span = max(values) - min(values) + 1
    if len(set(values)) / span < MIN_RANGE_COVERAGE:
        return False
    pairs = list(pairwise(values))
    increasing = sum(1 for a, b in pairs if b > a)
    if increasing / len(pairs) < MIN_INCREASING:
        return False
    steps = [b - a for a, b in pairs if b > a]
    return bool(steps) and median(steps) <= MAX_MEDIAN_STEP


def strip_line_numbers(doc: Document) -> Document:
    """Remove manuscript line numbers, if the document has them."""
    candidates = _candidates(doc)
    if not looks_like_line_numbering([v for _, _, v in candidates], _total_lines(doc)):
        return doc

    drop: dict[str, set[int]] = {}
    for block, line_index, _ in candidates:
        drop.setdefault(block.id, set()).add(line_index)

    removed = 0
    for block in doc.blocks:
        lines_to_drop = drop.get(block.id)
        if not lines_to_drop:
            continue
        lines = block.text.split("\n")
        kept = [line for i, line in enumerate(lines) if i not in lines_to_drop]
        removed += len(lines) - len(kept)
        block.text = "\n".join(kept)
        block.attrs["line_numbers_removed"] = len(lines) - len(kept)

    doc.note(
        "line_numbers",
        f"removed {removed} manuscript line numbers that were interleaved with the text",
        stage="clean",
        level=DiagnosticLevel.INFO,
    )
    return doc
