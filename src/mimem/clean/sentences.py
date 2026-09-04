"""Sentence segmentation.

A naive ``text.split('.')`` produces garbage on scientific prose: "Fig. 4", "et al.", "e.g.",
"0.0837", "vs.", "approx." are all sentence-internal. Since sentence length is a hard rule
(SENT-01) and segments are built out of sentences, getting this wrong corrupts the whole plan.

We use pysbd when it is available and fall back to a conservative regex splitter that knows the
abbreviations that matter in papers. Offsets are stored on the block rather than the text being
split, so provenance spans stay valid.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Protocol

from mimem.ir import BlockKind, Document

_NO_SPLIT_KINDS = frozenset({BlockKind.CODE, BlockKind.EQUATION, BlockKind.PAGE_ARTIFACT})

#: Abbreviations after which a period does *not* end a sentence.
ABBREVIATIONS = (
    "fig",
    "figs",
    "eq",
    "eqs",
    "ref",
    "refs",
    "tab",
    "no",
    "vs",
    "cf",
    "al",
    "et",
    "e.g",
    "i.e",
    "approx",
    "ca",
    "dr",
    "prof",
    "mr",
    "mrs",
    "ms",
    "st",
    "vol",
    "pp",
    "ed",
    "eds",
    "min",
    "max",
    "sec",
    "chap",
    "resp",
)

_ABBREV_RE = re.compile(
    r"(?:\b(?:" + "|".join(re.escape(a) for a in ABBREVIATIONS) + r")\.)\s*$",
    re.IGNORECASE,
)
_INITIAL_RE = re.compile(r"\b[A-Z]\.\s*$")
_DECIMAL_RE = re.compile(r"\d\.\s*$")
_BOUNDARY_RE = re.compile(r"(?<=[.!?])[\"')\]]*\s+")


class _Segmenter(Protocol):
    def segment(self, text: str) -> Any: ...


@lru_cache(maxsize=1)
def _pysbd_segmenter() -> Any | None:
    try:
        import pysbd

        return pysbd.Segmenter(language="en", clean=False, char_span=True)
    except Exception:  # pragma: no cover - optional path
        return None


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Character offsets of each sentence in ``text``."""
    if not text.strip():
        return []
    seg = _pysbd_segmenter()
    if seg is not None:
        try:
            spans = [(s.start, s.end) for s in seg.segment(text)]
            trimmed = [_trim(text, a, b) for a, b in spans]
            return [s for s in trimmed if s is not None]
        except Exception:  # pragma: no cover - pysbd occasionally trips on odd input
            pass
    return _regex_spans(text)


def _regex_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for m in _BOUNDARY_RE.finditer(text):
        head = text[start : m.start()]
        if _ABBREV_RE.search(head) or _INITIAL_RE.search(head) or _DECIMAL_RE.search(head):
            continue
        trimmed = _trim(text, start, m.start())
        if trimmed:
            spans.append(trimmed)
        start = m.end()
    tail = _trim(text, start, len(text))
    if tail:
        spans.append(tail)
    return spans


def _trim(text: str, start: int, end: int) -> tuple[int, int] | None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if end > start else None


def split_sentences(doc: Document) -> Document:
    """Fill ``block.sentences`` for every block that holds prose."""
    total = 0
    for block in doc.blocks:
        if block.kind in _NO_SPLIT_KINDS or not block.text.strip():
            block.sentences = []
            continue
        block.sentences = sentence_spans(block.text)
        total += len(block.sentences)
    doc.source.attrs["sentence_count"] = total
    return doc
