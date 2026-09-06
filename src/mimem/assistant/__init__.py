"""Driving mimem from an assistant: a local MCP server, a workspace, and a review log.

The pipeline produces a script. Two things are missing before that is useful: a voice, and
something that comes back tomorrow to ask you about it. An assistant cannot be the first — that
is still milestone M7 — but it can be the second, and it can also write the explanations that
otherwise need a paid API key.

See ``docs/PLAN-assistant.md`` for why it is shaped this way, including the two designs that did
not survive review.
"""

from mimem.assistant.review import Answer, CardState, ReviewLog, next_interval, select
from mimem.assistant.workspace import SourceError, Workspace, build, resolve_source, slugify

__all__ = [
    "Answer",
    "CardState",
    "ReviewLog",
    "SourceError",
    "Workspace",
    "build",
    "next_interval",
    "resolve_source",
    "select",
    "slugify",
]
