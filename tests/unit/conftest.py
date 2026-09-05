"""A small planned paper, shared by the planner tests and the lint fixture pairs.

Constructed rather than ingested: the planner tests are about structure, retrieval and spacing,
and a real PDF would put an extraction bug between the test and the thing it is testing. The
sections are deliberately long enough to survive ``MIN_SECTION_WORDS`` and to hold more than one
segment, because a one-segment section exercises none of the interesting paths.
"""

from __future__ import annotations

import pytest

from mimem.clean.sentences import sentence_spans
from mimem.concepts import build as build_registry
from mimem.config import Listener, Profile, load_profile
from mimem.ir import Block, BlockKind, BlockRole, Document, Script, SourceMeta, block_id
from mimem.plan import plan
from mimem.triage import triage

ABSTRACT = (
    "Capacity fade in lithium-ion cells is dominated by the solid electrolyte interphase, "
    "which consumes lithium at every cycle. We show that interphase repair, rather than "
    "particle fracture, sets the rate of capacity fade in silicon anodes. Coulombic "
    "efficiency is defined as the ratio of charge recovered to charge inserted."
)

INTRODUCTION = (
    "Silicon anodes expand by three hundred percent on lithiation. That expansion cracks the "
    "solid electrolyte interphase on every cycle. Repairing the solid electrolyte interphase "
    "consumes lithium inventory, because each repair grows fresh interphase from the "
    "electrolyte. Coulombic efficiency therefore falls below one, and the shortfall accumulates "
    "over hundreds of cycles. The solid electrolyte interphase is thus the central object of "
    "this study."
)

INTRODUCTION_2 = (
    "Earlier work attributed the same capacity fade to particle fracture, because cracked "
    "particles are easy to see in electron micrographs. Fracture is real, but it is not "
    "rate-limiting in the cells considered here. The distinction matters because it changes "
    "which lever raises cycle life: a binder that holds cracked particles together, or an "
    "electrolyte additive that stabilises the solid electrolyte interphase. Coulombic "
    "efficiency is the measurement that separates the two mechanisms, and it is cheap to make."
)

METHODS = (
    "Cells were cycled at zero point five C between three volts and four point two volts. "
    "Coulombic efficiency was measured on every cycle with a precision coulometer. The solid "
    "electrolyte interphase thickness was estimated from differential voltage analysis. "
    "Each condition was repeated on five cells to bound the scatter."
)

METHODS_2 = (
    "The precision coulometer resolves one part in one hundred thousand, which is what makes "
    "coulombic efficiency usable as a rate measurement rather than a pass or fail check. "
    "Differential voltage analysis was calibrated against cells opened after fifty cycles. "
    "Electrolyte composition was held fixed across every condition, so that the solid "
    "electrolyte interphase is the only variable that changes between the two groups."
)

RESULTS = (
    "Coulombic efficiency settled at nine nine point four percent after twenty cycles. "
    "Cells with the thicker solid electrolyte interphase lost capacity faster, which supports "
    "the repair mechanism. Particle fracture was detected in fewer than one in ten cells and "
    "does not explain the observed rate. The solid electrolyte interphase therefore governs "
    "the capacity fade we measure."
)

RESULTS_2 = (
    "The capacity fade rate tracks the reciprocal of coulombic efficiency across every "
    "condition tested, with no measurable contribution from the fractured cells. Cells held at "
    "forty degrees lost capacity three times faster, and their solid electrolyte interphase "
    "was correspondingly thicker. Lithium inventory, not electrode structure, is what runs out "
    "first in these silicon anodes."
)

CONCLUSION = (
    "Interphase repair, not fracture, sets the capacity fade of silicon anodes. Raising "
    "coulombic efficiency by one tenth of a percent doubles the cycle life. Electrolyte "
    "additives that stabilise the solid electrolyte interphase are therefore the lever worth "
    "pulling."
)

CONCLUSION_2 = (
    "The practical consequence is that a cell chemistry should be screened on coulombic "
    "efficiency before anything else is measured. A binder that suppresses particle fracture "
    "buys very little in these cells. The solid electrolyte interphase deserves the "
    "development effort, because it is where the lithium inventory goes."
)

PARTS: list[tuple[str, str, str, int | None]] = [
    ("heading", "title", "Interphase repair limits silicon anode life", 1),
    ("paragraph", "abstract", ABSTRACT, None),
    ("heading", "introduction", "1 Introduction", 1),
    ("paragraph", "introduction", INTRODUCTION, None),
    ("paragraph", "introduction", INTRODUCTION_2, None),
    ("heading", "methods", "2 Methods", 1),
    ("paragraph", "methods", METHODS, None),
    ("paragraph", "methods", METHODS_2, None),
    ("heading", "results", "3 Results", 1),
    ("paragraph", "results", RESULTS, None),
    ("paragraph", "results", RESULTS_2, None),
    ("heading", "conclusion", "4 Conclusion", 1),
    ("paragraph", "conclusion", CONCLUSION, None),
    ("paragraph", "conclusion", CONCLUSION_2, None),
]


def _block(kind: str, role: str, text: str, order: int, level: int | None = None) -> Block:
    return Block(
        id=block_id(kind, 1, order, text),
        kind=BlockKind(kind),
        role=BlockRole(role),
        text=text,
        order=order,
        page=1 + order // 3,
        level=level,
        sentences=sentence_spans(text),
    )


@pytest.fixture
def interphase_doc() -> Document:
    """A small paper: abstract plus four headed sections, triaged and ready to plan."""
    blocks = [
        _block(kind, role, text, i, level) for i, (kind, role, text, level) in enumerate(PARTS)
    ]
    doc = Document(
        id="d_test",
        source=SourceMeta(
            format="pdf",
            title="Interphase repair limits silicon anode life",
            authors=["Ada Lovelace", "Grace Hopper"],
        ),
        blocks=blocks,
    )
    return triage(doc)


@pytest.fixture
def study_profile() -> Profile:
    return load_profile("study")


@pytest.fixture
def interphase_script(interphase_doc: Document, study_profile: Profile) -> Script:
    registry = build_registry(interphase_doc, Listener())
    return plan(interphase_doc, registry, study_profile, Listener())
