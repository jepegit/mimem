"""Parentheses (rule SENT-03).

A parenthesis is a purely visual instruction: "hold this sentence in mind, take a detour, now
resume". A reader does it with their eyes for free. A listener has to do it in working memory,
mid-clause, with no way to see where the detour ends -- which is exactly the load the transient
information effect says they cannot afford.

So parentheses never survive into the audio track. Three treatments, by what is inside:

* an **acronym definition** -- "lithium-ion batteries (LIBs)" -- becomes an appositive:
  "lithium-ion batteries, or LIBs". The definition is the most useful thing in the sentence and
  the listener needs it, they just cannot see the brackets;
* a **short aside** becomes a comma-delimited appositive, which is what the author would have
  said out loud;
* a **long aside** is dropped. If it were essential it would not have been in brackets.
"""

from __future__ import annotations

import re

#: An acronym as journals write them: capitals, sometimes with digits or a trailing plural s.
ACRONYM = re.compile(r"^[A-Z][A-Za-z0-9]{0,9}s?$")

#: Above this many words, a parenthetical is a digression rather than an apposition.
MAX_ASIDE_WORDS = 8

_PAREN = re.compile(r"\s*\(([^()]{1,300})\)")
_TIDY = (
    (re.compile(r",\s*([.,;:!?])"), r"\1"),
    (re.compile(r",\s*,"), ","),
    (re.compile(r"\s{2,}"), " "),
    (re.compile(r"\s+([.,;:!?])"), r"\1"),
)


def _replace(match: re.Match[str]) -> str:
    inner = match.group(1).strip(" ,;:")
    if not inner:
        return ""
    if ACRONYM.match(inner):
        return f", or {inner},"
    if len(inner.split()) <= MAX_ASIDE_WORDS:
        return f", {inner},"
    return ""


def verbalize_parentheticals(text: str) -> str:
    """Rewrite or remove every parenthetical in ``text``."""
    # Twice, so that a nested pair -- rare, but real -- is resolved from the inside out.
    for _ in range(2):
        new = _PAREN.sub(_replace, text)
        if new == text:
            break
        text = new
    # Square brackets that survived citation removal hold editorial insertions; keep the words.
    text = re.sub(r"\s*\[([^\[\]]{1,120})\]", r" \1", text)
    for pattern, replacement in _TIDY:
        text = pattern.sub(replacement, text)
    return text.strip()
