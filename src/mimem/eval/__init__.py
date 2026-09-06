"""Evaluation: the first time any of this gets measured rather than argued from the literature.

Three layers were planned (PLAN section 8). This is layer 1 -- mechanical, free, and run on
every build. Layer 2 (feed ``audio.md`` to a fresh model and ask it the cards' own questions)
and layer 3 (people) are still ahead, and the numbers here are not a substitute for either: they
measure whether the programme still has the properties the design asks for, not whether anybody
learned anything.
"""

from mimem.eval.harness import (
    BASELINE,
    CORPUS,
    as_json,
    documents,
    load_baseline,
    run,
    save_baseline,
    table,
)
from mimem.eval.metrics import Corpus, Metrics, measure

__all__ = [
    "BASELINE",
    "CORPUS",
    "Corpus",
    "Metrics",
    "as_json",
    "documents",
    "load_baseline",
    "measure",
    "run",
    "save_baseline",
    "table",
]
