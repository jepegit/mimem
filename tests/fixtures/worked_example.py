"""The worked example: one paragraph, and what each task should say about it.

Lives here rather than in a test module because two of them use it, and rather than in
``conftest`` because there are two conftest files and ``from conftest import`` resolves to
whichever is nearer. ``tests/fixtures`` is already on ``sys.path``.

The answers are scripted rather than recorded from a model, deliberately: the tests that use
them check plumbing, the grounding gate and beat structure, none of which should depend on what
a model happens to say on a given day.
"""

from __future__ import annotations

from mimem.clean.sentences import sentence_spans
from mimem.ir import Block, BlockKind, BlockRole, Document, SourceMeta, block_id
from mimem.triage import triage

# The source paragraph from docs/examples/sample-output.md, section A. The milestone is done
# when the pipeline can turn *this* into the rendering in section C.
SOURCE_PARAGRAPH = (
    "Electrolyte decomposition at the negative electrode leads to the formation of a solid "
    "electrolyte interphase (SEI), which passivates the surface and limits further reduction. "
    "However, the SEI is not static: repeated volume changes of the active material during "
    "delithiation, which can exceed 300 % for silicon-based anodes, fracture the layer and "
    "expose fresh surface, consuming additional lithium inventory. The resulting capacity loss "
    "was measured at 0.0837 % per cycle over 500 cycles, a retention of 82.1 % at end of test."
)

CONTEXT = (
    "The solid electrolyte interphase refers to the passivating layer that forms on the "
    "negative electrode during the first charge. "
    "Silicon anodes swell on lithiation and the solid electrolyte interphase cracks. "
    "Each repair of the solid electrolyte interphase consumes lithium that never returns. "
    "The thickness of the solid electrolyte interphase increases over the first hundred cycles. "
    "The solid electrolyte interphase is therefore the object of this study."
)

# What the target rendering says, in the shape each task returns it.
ANSWERS = {
    "gloss": [
        {
            "short_def": "a thin crust that forms on the negative electrode during the first charges",
            "long_def": (
                "The electrolyte touching the negative electrode is unstable there, so a little "
                "of it decomposes and the products build a layer. Once that layer covers the "
                "surface it blocks the reaction that created it."
            ),
            "spoken": None,
        }
    ],
    "anchor": [
        {
            "text": (
                "a cast-iron pan that seasons itself: the first heating burns a thin layer onto "
                "the metal, and that burnt layer is what stops the metal rusting further"
            )
        }
    ],
    "why": [
        {
            "text": (
                "The crust is brittle and the particle underneath it is not staying still, so "
                "every swing cracks it and every repair costs lithium."
            )
        }
    ],
    "analogy": [
        {
            "text": "it is like a scab that keeps being knocked off and re-formed",
            "limit": "a scab heals from the body's own store, and this one is paid for out of the cell",
        }
    ],
}


def _doc(text: str = SOURCE_PARAGRAPH, context: str = CONTEXT) -> Document:
    parts = [
        ("heading", "title", "Interphase repair limits silicon anode life"),
        ("paragraph", "abstract", text),
        ("heading", "introduction", "1 Introduction"),
        ("paragraph", "introduction", context),
    ]
    blocks = [
        Block(
            id=block_id(kind, 1, i, body),
            kind=BlockKind(kind),
            role=BlockRole(role),
            text=body,
            order=i,
            page=1,
            level=1 if kind == "heading" else None,
            sentences=sentence_spans(body),
        )
        for i, (kind, role, body) in enumerate(parts)
    ]
    return triage(
        Document(
            id="d_sample",
            source=SourceMeta(
                format="pdf",
                title="Interphase repair limits silicon anode life",
                authors=["A. Researcher"],
            ),
            blocks=blocks,
        )
    )
