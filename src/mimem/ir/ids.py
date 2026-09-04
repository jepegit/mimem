"""Stable, content-derived identifiers.

Every artefact in mimem is re-derivable from its input. That is only useful if the IDs are
stable too: a re-run over an unchanged source must produce the same block IDs, so that caches
hit, diffs are readable, and ``mimem explain`` can point at a beat from a previous run.

IDs are therefore hashes of content, never counters or UUIDs.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_ID_LEN = 12


def _digest(*parts: object) -> str:
    h = hashlib.blake2s(digest_size=16)
    for part in parts:
        h.update(str(part).encode("utf-8", errors="replace"))
        h.update(b"\x1f")  # unit separator, so ("ab","c") != ("a","bc")
    return h.hexdigest()[:_ID_LEN]


def block_id(kind: str, page: int | None, order: int, text: str) -> str:
    """ID for a block.

    ``order`` is included because a document may legitimately repeat identical text (a
    running head, a repeated axis label), and those are different blocks.
    """
    return "b_" + _digest(kind, page, order, text[:400])


def asset_id(block: str, kind: str, index: int) -> str:
    return "a_" + _digest(block, kind, index)


def document_id(source_sha256: str, adapter: str) -> str:
    """ID for a document: the same file through a different adapter is a different document."""
    return "d_" + _digest(source_sha256, adapter)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
