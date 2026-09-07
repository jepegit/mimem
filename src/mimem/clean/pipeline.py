"""Stage 2: turn an adapter's output into a clean, corpus-level document.

Order matters and is not negotiable:

0. **extraction artifacts** -- control characters and math placeholders, before anything
   tries to read the text as language.
1. **line numbers** -- must run early, while the line structure still exists. A manuscript
   line number sitting between ``recov-`` and ``ery`` defeats dehyphenation completely.
2. **stacked headings** -- must run while the extractor's line breaks are still there; a
   section heading and its first subsection arrive as one block, and once the lines are joined
   there is nothing left to split on.
3. **dehyphenate** -- must run before anything reads words, or terms are split in half.
4. **page artifacts** -- needs page geometry, which later steps do not preserve.
5. **merge** -- needs artifacts already removed, or a running head glues two paragraphs
   together; and must run before sections, because merging rewrites block IDs.
6. **sections** -- assigns the IDs that everything downstream references.
7. **figures** -- pairs captions with the fragments they speak for; needs page geometry, which
   survives this far, and section IDs, which it records against.
8. **sentences** -- last, so it segments final text.
"""

from __future__ import annotations

from mimem.clean.artifacts import strip_page_artifacts
from mimem.clean.dehyphenate import dehyphenate
from mimem.clean.extraction import strip_extraction_artifacts
from mimem.clean.figures import link_figures
from mimem.clean.headings import split_stacked_headings
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

    strip_extraction_artifacts(doc)
    strip_line_numbers(doc)
    split_stacked_headings(doc)
    dehyphenate(doc)
    strip_page_artifacts(doc)
    if drop_empty:
        _drop_empty(doc)
    merge_continuations(doc)
    assign_sections(doc)
    link_figures(doc)
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
