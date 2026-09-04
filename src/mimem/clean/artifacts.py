"""Running heads, folios and other page furniture.

These are the purest case of rule COH-01: text that exists for the printed page and carries no
information for a listener. "J. Power Sources 512 (2021) 230512" narrated forty times is the
kind of thing that makes people give up on audio.

Detection is by repetition and position rather than by pattern matching, so it works for
journals we have never seen.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict

from mimem.ir import BlockKind, DiagnosticLevel, Document

#: How far from the top/bottom edge of the page's text area a block must sit to be furniture.
EDGE_BAND = 0.12

#: A candidate must repeat on at least this many pages, and on this fraction of them. Two pages
#: is the floor: a short paper still has a running head, and one repetition is enough evidence
#: when the block also sits in the edge band.
MIN_REPEATS = 2
MIN_FRACTION = 0.30

_DIGITS = re.compile(r"\d+")
_WS = re.compile(r"\s+")


def _signature(text: str) -> str:
    """Normalise away the parts that change from page to page (the page number, mostly)."""
    return _WS.sub(" ", _DIGITS.sub("#", text.strip().lower()))[:120]


def strip_page_artifacts(doc: Document) -> Document:
    """Mark repeated header/footer blocks as :attr:`BlockKind.PAGE_ARTIFACT`."""
    pages = {b.page for b in doc.blocks if b.page is not None}
    if len(pages) < 2:
        return doc

    bounds: dict[int, tuple[float, float]] = {}
    for page in pages:
        ys = [b.bbox for b in doc.blocks if b.page == page and b.bbox is not None]
        if ys:
            bounds[page] = (min(b.y0 for b in ys), max(b.y1 for b in ys))

    candidates: dict[str, set[int]] = defaultdict(set)
    edge_blocks: dict[str, list[str]] = defaultdict(list)
    for block in doc.blocks:
        if block.page is None or block.bbox is None or not block.text.strip():
            continue
        if block.kind in {BlockKind.FIGURE, BlockKind.TABLE}:
            continue
        top, bottom = bounds.get(block.page, (0.0, 0.0))
        height = max(bottom - top, 1.0)
        rel_top = (block.bbox.y0 - top) / height
        rel_bottom = (bottom - block.bbox.y1) / height
        if min(rel_top, rel_bottom) > EDGE_BAND:
            continue
        if len(block.text) > 200:
            continue
        sig = _signature(block.text)
        candidates[sig].add(block.page)
        edge_blocks[sig].append(block.id)

    threshold = max(MIN_REPEATS, math.ceil(MIN_FRACTION * len(pages)))
    marked = 0
    for sig, seen_pages in candidates.items():
        if len(seen_pages) < threshold:
            continue
        for block_id in edge_blocks[sig]:
            block = doc.block(block_id)
            if block.kind is BlockKind.PAGE_ARTIFACT:
                continue
            block.kind = BlockKind.PAGE_ARTIFACT
            block.attrs["artifact_reason"] = f"repeats on {len(seen_pages)} pages"
            marked += 1

    if marked:
        doc.note(
            "page_artifacts",
            f"marked {marked} repeated header/footer blocks across {len(pages)} pages",
            stage="clean",
            level=DiagnosticLevel.INFO,
        )
    return doc
