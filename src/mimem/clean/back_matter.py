"""The point where a paper stops arguing and starts crediting people (rule COH-01).

Triage already drops a block that *is* back matter. This is for the block that back matter is
stuck to. Two of twelve corpus papers run the whole of it -- author information, contributions,
competing interests, acknowledgements and the reference list -- onto the end of the concluding
paragraph, and the abstract onto the front of the keyword list. Neither block can be dropped;
both carry the argument. So the block is cut in two at the boundary, and triage decides about
each half on its own.

Detection is a recognised heading in a heading's *position*, not a keyword anywhere in the text.
"described in the Supporting Information" is a sentence about a paper; "■ASSOCIATED CONTENT
* S Supporting Information" is where the paper ends.
"""

from __future__ import annotations

import re

from mimem.ir import Block, BlockKind, DiagnosticLevel, Document, block_id

_STAGE = "back_matter"

#: The headings a journal puts over its back matter, in the order they are usually printed.
#: Matched case-insensitively and then required to *start* with a capital, which is what
#: separates the heading "Notes" from a sentence that happens to mention notes.
HEADINGS = (
    "associated content",
    "author information",
    "author contributions",
    "acknowledgments",
    "acknowledgements",
    "acknowledgment",
    "acknowledgement",
    "conflicts of interest",
    "conflict of interest",
    "competing financial interests",
    "competing interests",
    "declaration of competing interest",
    "declarations of interest",
    "data availability",
    "supporting information",
    "abbreviations",
    "references",
    "keywords",
    "key words",
    "funding",
    "notes",
)

#: The bullet a journal sets its section headings with. ACS uses a filled square, and it is the
#: single most reliable signal in the corpus: every one of them opens a back-matter section.
MARKERS = "■▪●◆•"

#: A heading in a heading's position: after a marker, or after a sentence has ended.
BOUNDARY = re.compile(
    r"(?:(?<=[.!?])\s+|\s*(?=[" + MARKERS + r"]))"
    r"[" + MARKERS + r"]?\s*"
    r"(?P<heading>" + "|".join(HEADINGS) + r")\b",
    re.IGNORECASE,
)

#: What may follow the heading. A colon, the end of the block, a marker, or a capital letter --
#: anything that reads as the start of new material rather than as the rest of a sentence.
#: Without this, "References to earlier work suggest" ends the paper at the word "References".
_HEADING_FOLLOWS = re.compile(r"\s*(?::|$|[" + MARKERS + r"*⊥†‡]|[A-Z(])")

#: Below this many characters in front of it, the boundary is at the start of the block and
#: there is nothing to keep -- which is triage's business, not this module's.
MIN_KEPT = 40


def find_boundary(text: str) -> int | None:
    """Where the back matter starts in ``text``, or ``None`` if it does not."""
    for match in BOUNDARY.finditer(text):
        if not match.group("heading")[0].isupper():
            continue  # "described in the supporting information" is a sentence
        if not _HEADING_FOLLOWS.match(text, match.end()):
            continue  # "References to earlier work" is a subject, not a heading
        if match.start() < MIN_KEPT:
            return None  # the whole block is back matter; let triage drop it whole
        return match.start()
    return None


def split_back_matter(doc: Document) -> Document:
    """Cut a paragraph in two where its back matter begins."""
    out: list[Block] = []
    split = 0

    for block in doc.blocks:
        cut = (
            find_boundary(block.text) if block.kind is BlockKind.PARAGRAPH and block.text else None
        )
        if cut is None:
            out.append(block)
            continue
        head, tail = block.text[:cut].rstrip(), block.text[cut:].strip()
        split += 1
        out.append(block.model_copy(update={"text": head}))
        out.append(
            block.model_copy(
                update={
                    "id": block_id(block.kind.value, block.page, block.order, tail),
                    "text": tail,
                    "attrs": {**block.attrs, "split_from": block.id},
                }
            )
        )

    if split:
        doc.blocks = out
        doc.renumber()
        doc.note(
            _STAGE,
            f"split back matter off the end of {split} paragraph(s)",
            stage="clean",
            level=DiagnosticLevel.INFO,
        )
    return doc
