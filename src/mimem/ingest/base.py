"""Adapter contract and registry.

Every adapter returns a :class:`~mimem.ir.models.Document`; nothing downstream knows the source
format. New formats are new adapters, never new branches downstream (PLAN section 4, stage 1).

Adapters are responsible for *format-specific* structure: layout, reading order, columns,
embedded assets. Everything corpus-level -- dehyphenation, running heads, sections, sentence
splitting -- happens in :mod:`mimem.clean`, so it is written once and tested once.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, TypeVar

from mimem.ir import Document


class IngestError(RuntimeError):
    """The source could not be read at all. Recoverable problems become diagnostics instead."""


class Adapter(ABC):
    """What every ingestion adapter must provide.

    ``version`` is part of the contract: it goes into ``SourceMeta`` and therefore into the
    cache key, so bumping it after changing extraction behaviour invalidates stale artefacts.
    """

    name: ClassVar[str] = "unknown"
    version: ClassVar[str] = "0"
    extensions: ClassVar[tuple[str, ...]] = ()

    @abstractmethod
    def load(self, path: Path) -> Document:
        """Read ``path`` into the canonical IR."""


A = TypeVar("A", bound=type[Adapter])

_ADAPTERS: list[type[Adapter]] = []


def register(cls: A) -> A:
    """Class decorator: make an adapter discoverable by :func:`adapter_for`."""
    _ADAPTERS.append(cls)
    return cls


def adapter_for(path: Path) -> Adapter:
    """Pick an adapter by file extension.

    Adapters with optional dependencies raise :class:`IngestError` at construction time with an
    actionable message, rather than failing with an ImportError deep in a call stack.
    """
    suffix = path.suffix.lower()
    for cls in _ADAPTERS:
        if suffix in cls.extensions:
            return cls()
    known = sorted({e for cls in _ADAPTERS for e in cls.extensions})
    raise IngestError(f"no adapter for '{suffix}' (known: {', '.join(known)})")


def load(path: str | Path) -> Document:
    """Ingest a file into the canonical document IR."""
    p = Path(path)
    if not p.exists():
        raise IngestError(f"no such file: {p}")
    if p.is_dir():
        raise IngestError(f"{p} is a directory")
    return adapter_for(p).load(p)


def available_extensions() -> list[str]:
    return sorted({e for cls in _ADAPTERS for e in cls.extensions})
