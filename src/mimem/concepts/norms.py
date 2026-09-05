"""Concreteness: how imageable a word is.

The concreteness effect is one of the most replicated findings in memory research (knowledge
base §3.1), and it is what rule IMG-01 keys on: an abstract, important idea earns a concrete
anchor, a concrete one does not need it. So we need a number for "how abstract is this phrase".

Two sources, in order:

**Brysbaert, Warriner & Kuperman (2014)** -- human concreteness ratings for about 40 000 English
lemmas on a 1--5 scale. This is the real signal, it is free, and it is a plain CSV. It is not
vendored here because it is someone else's dataset with its own terms; point mimem at your copy
with ``MIMEM_CONCRETENESS_FILE`` or drop it at ``data/concreteness.csv``.

**A morphological fallback** -- used when the norms are absent, so the pipeline works out of the
box. English marks abstraction in its suffixes: *-tion*, *-ity*, *-ness*, *-ism* nominalise a
process or a property into something you cannot photograph. It is a much blunter instrument than
the norms and it says so: :func:`status` reports which source is live, and the fallback is
deliberately conservative, because wrongly calling a concrete term abstract spends an anchor on
something that never needed one.
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from mimem.config import REPO_ROOT

#: Where a downloaded copy of the Brysbaert norms is looked for.
DEFAULT_NORMS_PATH = REPO_ROOT / "data" / "concreteness.csv"
NORMS_ENV_VAR = "MIMEM_CONCRETENESS_FILE"

#: The Brysbaert scale: 1 = maximally abstract, 5 = maximally concrete.
SCALE_MIN, SCALE_MAX = 1.0, 5.0
NEUTRAL = 3.0

#: Suffixes that nominalise a process or property into something unimageable.
ABSTRACT_SUFFIXES = (
    "ability", "ibility", "ization", "isation", "ivity", "ality", "ility",
    "ness", "ment", "ance", "ence", "tion", "sion", "ism", "ity", "ology",
    "ory", "acy", "ure", "ency", "ancy",
)  # fmt: skip

#: Suffixes and stems that point the other way: things with edges.
CONCRETE_SUFFIXES = ("ode", "ite", "ide", "ell", "ube", "ayer", "ile", "ate", "ode")

_WORD = re.compile(r"[A-Za-z][a-z'-]+")


@dataclass(frozen=True)
class NormsStatus:
    source: str  # "brysbaert" | "morphology"
    entries: int
    path: Path | None


@lru_cache(maxsize=1)
def _table() -> tuple[dict[str, float], Path | None]:
    """Load the concreteness table once, or return an empty one."""
    candidate = os.environ.get(NORMS_ENV_VAR)
    path = Path(candidate) if candidate else DEFAULT_NORMS_PATH
    if not path.exists():
        return {}, None

    table: dict[str, float] = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        delimiter = "\t" if "\t" in sample.splitlines()[0] else ","
        for row in csv.DictReader(fh, delimiter=delimiter):
            word = (row.get("Word") or row.get("word") or "").strip().lower()
            raw = row.get("Conc.M") or row.get("conc_m") or row.get("concreteness")
            if not word or not raw:
                continue
            try:
                table[word] = float(raw)
            except ValueError:
                continue
    return table, path


def status() -> NormsStatus:
    """Which concreteness source is live. Reported by ``mimem concepts`` so the difference
    between a measured score and a morphological guess is never invisible."""
    table, path = _table()
    if table:
        return NormsStatus(source="brysbaert", entries=len(table), path=path)
    return NormsStatus(source="morphology", entries=0, path=None)


def _morphological_concreteness(word: str) -> float:
    lowered = word.lower()
    if len(lowered) <= 3:
        return NEUTRAL
    if lowered.endswith(ABSTRACT_SUFFIXES):
        return 1.8
    if lowered.endswith(CONCRETE_SUFFIXES):
        return 4.0
    # Long Latinate words skew abstract; short Germanic ones skew concrete.
    if len(lowered) >= 11:
        return 2.5
    if len(lowered) <= 5:
        return 3.6
    return NEUTRAL


def concreteness(word: str) -> float:
    """Concreteness of a single word on the 1--5 Brysbaert scale."""
    table, _ = _table()
    lowered = word.lower().strip("-'")
    if lowered in table:
        return table[lowered]
    if table and lowered.endswith("s") and lowered[:-1] in table:
        return table[lowered[:-1]]
    return _morphological_concreteness(lowered)


def phrase_concreteness(phrase: str) -> float:
    """Mean concreteness of the content words in a phrase."""
    words = _WORD.findall(phrase)
    if not words:
        return NEUTRAL
    scores = [concreteness(w) for w in words]
    return sum(scores) / len(scores)


def abstractness(phrase: str) -> float:
    """0 (utterly concrete) to 1 (utterly abstract) -- the form the scorer wants."""
    value = phrase_concreteness(phrase)
    clamped = max(SCALE_MIN, min(SCALE_MAX, value))
    return (SCALE_MAX - clamped) / (SCALE_MAX - SCALE_MIN)
