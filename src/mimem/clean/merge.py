"""Rejoin paragraphs that the page split.

A paragraph interrupted by a column break, a page break or a floating figure arrives as two or
more blocks. Left alone, the seam becomes a sentence boundary that was never there -- and in
audio, a full stop in the middle of a clause is audible and confusing.

Merging is conservative: it happens only where the text itself says it was interrupted (no
terminal punctuation before, a lowercase continuation after), and the merged block keeps a
record of what it was made from.
"""

from __future__ import annotations

import re

from mimem.ir import Block, BlockKind, DiagnosticLevel, Document, block_id

MERGEABLE = frozenset({BlockKind.PARAGRAPH})

#: Blocks that may sit *between* two halves of one paragraph without ending it.
#:
#: This is the whole reason the module exists and it was the one thing it did not do. A page
#: break puts a running head and a folio between the two halves, so they are never adjacent, so
#: they were never merged -- and the seam became a sentence boundary that was never there. On a
#: ninety-eight page review that left thirty-one beats opening mid-clause: "voltage and
#: temperature signals, achieving eight to thirteen minutes advanced warning", spoken as if it
#: were a sentence.
#:
#: A textless figure is here for the same reason and is named in the docstring above: artwork
#: floating in the middle of a column interrupts the text around it without ending it.
TRANSPARENT = frozenset({BlockKind.PAGE_ARTIFACT, BlockKind.FIGURE})


def _transparent(block: Block) -> bool:
    return block.kind in TRANSPARENT and not (block.kind is BlockKind.FIGURE and block.text.strip())


#: Something that plausibly ends a paragraph. A lone reference marker or a hyphen does not.
_TERMINAL = re.compile(r"[.!?:;]['\")\]]?\s*$")
_ENDS_OPEN = re.compile(r"[-,(\[]\s*$")
_STARTS_LOWER = re.compile(r"^\s*[a-z(\[]")
_ABBREV_END = re.compile(r"\b(?:e\.g|i\.e|cf|vs|et al|Fig|Eq|Ref|approx|ca)\.\s*$", re.IGNORECASE)


def _continues(prev: Block, nxt: Block) -> bool:
    if prev.kind not in MERGEABLE or nxt.kind not in MERGEABLE:
        return False
    left, right = prev.text.rstrip(), nxt.text.lstrip()
    if not left or not right:
        return False
    if _ENDS_OPEN.search(left):
        return True
    if _ABBREV_END.search(left):
        return True  # "... e.g." never ends a paragraph
    if _TERMINAL.search(left):
        return False
    return bool(_STARTS_LOWER.match(right))


def _last_mergeable(blocks: list[Block]) -> Block | None:
    """The most recent block a paragraph could continue from, looking past page furniture."""
    for block in reversed(blocks):
        if _transparent(block):
            continue
        return block
    return None


def merge_continuations(doc: Document) -> Document:
    """Merge paragraph blocks that are really one paragraph, across the page furniture between."""
    merged_blocks: list[Block] = []
    merges = 0

    for block in doc.blocks:
        prev = _last_mergeable(merged_blocks)
        if prev is not None and _continues(prev, block):
            sources = list(prev.attrs.get("merged_from") or [prev.id])
            sources.append(block.id)
            joiner = "" if prev.text.rstrip().endswith("-") else " "
            prev.text = f"{prev.text.rstrip()}{joiner}{block.text.lstrip()}"
            prev.attrs["merged_from"] = sources
            # The ID is content-derived, so it has to follow the content.
            prev.id = block_id(prev.kind.value, prev.page, prev.order, prev.text)
            if block.page is not None and block.page != prev.page:
                prev.attrs["spans_pages"] = True
            merges += 1
            continue
        merged_blocks.append(block)

    doc.blocks = merged_blocks
    doc.renumber()
    if merges:
        doc.note(
            "merged_paragraphs",
            f"rejoined {merges} paragraph fragments split by column or page breaks",
            stage="clean",
            level=DiagnosticLevel.INFO,
        )
    return doc
