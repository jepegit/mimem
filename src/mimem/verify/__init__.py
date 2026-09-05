"""Checking generated text against the source it claims to come from (rules ``GRD-*``).

This module exists because of one sentence in the design rules: *a flipped sign or a mangled
number is the worst failure this system can produce*. A listener who is told the capacity rose
when it fell has been actively misinformed, and unlike a clumsy sentence there is nothing in the
audio to warn them.

Two layers, in increasing cost and decreasing certainty.

**Deterministic checks (``GRD-03``)** — every number, year, name and directional claim in
generated text is looked up in the source spans it was written from. This needs no model, runs
on every build, and catches the failure modes that matter most. It is what
:func:`check` does, and it is the reason the elaboration layer can be trusted at all.

**Entailment (``GRD-02``)** — whether the *meaning* of a generated sentence follows from its
spans is a judgement, and lives in :mod:`mimem.llm.tasks.verify` as a separate model call. When
no model is configured the verdict is ``None`` -- unknown, not passed. A missing check and a
passed check must never look the same in the manifest.
"""

from mimem.verify.grounding import (
    DIRECTIONS,
    Finding,
    Severity,
    check,
    numbers_in,
    verdict,
)

__all__ = [
    "DIRECTIONS",
    "Finding",
    "Severity",
    "check",
    "numbers_in",
    "verdict",
]
