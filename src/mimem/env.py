"""Read a ``.env`` file, because putting a key in one is the obvious thing to do.

It was not being read. ``Settings`` is a ``BaseSettings`` with ``env_prefix="MIMEM_"``, and the
keys that matter are not mimem's own: ``ANTHROPIC_API_KEY`` is read by the Anthropic SDK
straight from ``os.environ``, ``OPENAI_API_KEY`` and ``ELEVENLABS_API_KEY`` by the adapters
here. None of that goes through pydantic, so a ``.env`` sat there doing nothing while
``mimem doctor`` said "no key" and told the user to export a variable they had already written
down.

**A real environment variable always wins.** ``export ANTHROPIC_API_KEY=...`` in the shell you
are standing in is a more deliberate act than a file you edited last month, and a file that
silently overrode it would be an afternoon nobody enjoys. This is dotenv's own default and it
is the right way round.

**Values are never logged.** :func:`loaded_from` returns the path, so ``doctor`` can say *where*
a key came from -- which is the actually useful half, and the half you can print.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Set once the search has run, so repeated CLI helpers do not re-read the file.
_searched = False
_source: Path | None = None

#: The variables worth reporting as coming from a file. Not a filter on what is loaded -- a
#: ``.env`` may hold anything -- only on what :func:`names_in` will name out loud.
KNOWN_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ELEVENLABS_API_KEY")


def load(start: Path | None = None, *, override: bool = False) -> Path | None:
    """Load the nearest ``.env`` into the environment, and return where it came from.

    Searches upward from ``start`` (the working directory by default), so running mimem from a
    subdirectory of a project still finds the file at its root.

    Idempotent: called from both the CLI and the MCP server entry points, which in one process
    is the same file twice.
    """
    global _searched, _source
    if _searched and not override:
        return _source

    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:  # pragma: no cover - it ships with pydantic-settings
        _searched = True
        return None

    found = find_dotenv(usecwd=True) if start is None else str(_nearest(start))
    _searched = True
    if not found or not Path(found).is_file():
        _source = None
        return None

    # override=False: a variable already in the environment stays. A file must not quietly
    # replace what the user typed in this shell.
    load_dotenv(found, override=override)
    _source = Path(found)
    return _source


def _nearest(start: Path) -> Path:
    for directory in (start, *start.parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return start / ".env"


def loaded_from() -> Path | None:
    """Where the ``.env`` was read from, if one was. Never its contents."""
    return _source


def names_in(path: Path | None = None) -> list[str]:
    """The known key *names* the file sets. Names only -- values are not read out.

    Enough for ``doctor`` to say "this came from your .env" rather than leaving a user to
    wonder whether the file was seen at all, and not enough to leak anything.
    """
    target = path or _source
    if target is None or not target.is_file():
        return []
    found: list[str] = []
    for line in target.read_text(encoding="utf-8", errors="replace").splitlines():
        name, sep, _ = line.partition("=")
        cleaned = name.strip().removeprefix("export ").strip()
        if sep and cleaned in KNOWN_KEYS:
            found.append(cleaned)
    return found


def is_from_file(name: str) -> bool:
    """Did this variable come from the ``.env`` rather than the shell?

    Only meaningful after :func:`load`, and only approximately: if both set it, the shell won
    and this still reports the file, because the file does mention it. ``doctor`` uses it to
    point at the right place when a key is wrong, so "your .env mentions this" is the useful
    claim rather than "this exact value came from there".
    """
    return name in names_in() and bool(os.environ.get(name))
