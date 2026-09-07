"""Split a heading block that is really two headings.

A section heading immediately followed by its first subsection heading -- "2.3. Core ML Models
and Training Strategies" and then "2.3.1. Model Architectures" -- is set with no paragraph
between, so a PDF extractor hands both back as one block. Later stages join the lines, and the
result is a section whose title is two titles:

    2.3. Core ML Models and Training Strategies 2.3.1. Model Architectures and General Workflow

Which the programme then reads out, numbering and all, as the name of a part.

This runs early, while the line breaks the extractor preserved are still there. Once they have
been collapsed to spaces there is nothing left to split on but the numbering itself, and by then
a heading and a sentence that happens to start with a figure number look the same.

Conservative on purpose: a line only starts a new heading if it opens with a *multi-level*
number. "1. Introduction" on its own line under a heading is far more likely to be the first
item of a list than a stacked heading, and splitting a list into headings would invent sections.
"""

from __future__ import annotations

import re

from mimem.ir import Block, BlockKind, Document, block_id

_STAGE = "headings"

#: A line that begins a numbered subsection: "2.1.1. Public Datasets", "3.1 Early Warning".
#: At least two levels, so an ordinary numbered list item does not qualify.
STACKED_HEADING = re.compile(r"^\s*\d+(?:\.\d+)+\.?\s+\S")


def split_stacked_headings(doc: Document) -> Document:
    """Split heading blocks that hold more than one heading, keeping reading order."""
    out: list[Block] = []
    split = 0

    for block in doc.blocks:
        parts = _parts(block)
        if len(parts) == 1:
            out.append(block)
            continue
        split += len(parts) - 1
        for index, text in enumerate(parts):
            out.append(
                block.model_copy(
                    update={
                        "id": block_id(block.kind.value, block.page, block.order, text),
                        "text": text,
                        "attrs": {**block.attrs, "split_from": block.id} if index else block.attrs,
                    }
                )
            )

    if split:
        doc.blocks = out
        doc.renumber()
        doc.note(_STAGE, f"split {split} stacked heading(s) into their own blocks", stage="clean")
    return doc


def _parts(block: Block) -> list[str]:
    if block.kind is not BlockKind.HEADING or "\n" not in block.text:
        return [block.text]

    parts: list[str] = []
    current: list[str] = []
    for line in block.text.split("\n"):
        if current and STACKED_HEADING.match(line):
            parts.append("\n".join(current))
            current = []
        current.append(line)
    if current:
        parts.append("\n".join(current))
    return [p for p in parts if p.strip()] or [block.text]
