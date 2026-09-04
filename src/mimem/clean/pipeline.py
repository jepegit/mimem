"""Stage 2: turn an adapter's output into a clean, corpus-level document.

Order matters and is not negotiable:

0. **line numbers** -- must run first, while the line structure still exists. A manuscript
   line number sitting between ``recov-`` and ``ery`` defeats dehyphenation completely.
1. **dehyphenate** -- must run before anything reads words, or terms are split in half.
2. **page artifacts** -- needs page geometry, which later steps do not preserve.
3. **merge** -- needs artifacts already removed, or a running head glues two paragraphs
   together; and must run before sections, because merging rewrites block IDs.
4. **sections** -- assigns the IDs that everything downstream references.
5. **sentences** -- last, so it segments final text.
"""

from __future__ import annotations

from mimem.clean.artifacts import strip_page_artifacts
from mimem.clean.dehyphenate import dehyphenate
from mimem.clean.line_numbers import strip_line_numbers
from mimem.clean.merge import merge_continuations
from mimem.clean.sections import assign_sections
from mimem.clean.sentences import split_sentences
from mimem.ir import BlockKind, Document

_STAGE = "clean"


def clean(doc: Document, *, drop_empty: bool = True) -> Document:
    """Run the full cleanup pipeline. Idempotent: running it twice changes nothing."""
    if _STAGE in doc.stages:
        return doc

    strip_line_numbers(doc)
    dehyphenate(doc)
    strip_page_artifacts(doc)
    if drop_empty:
        _drop_empty(doc)
    merge_continuations(doc)
    assign_sections(doc)
    split_sentences(doc)

    doc.renumber()
    doc.stages.append(_STAGE)
    return doc


def _drop_empty(doc: Document) -> None:
    """Remove blocks with no text, keeping the ones whose payload is not text."""
    keep_kinds = {BlockKind.FIGURE, BlockKind.TABLE}
    before = len(doc.blocks)
    doc.blocks = [b for b in doc.blocks if b.text.strip() or b.kind in keep_kinds]
    removed = before - len(doc.blocks)
    if removed:
        doc.note("dropped_empty", f"removed {removed} empty blocks", stage=_STAGE)
