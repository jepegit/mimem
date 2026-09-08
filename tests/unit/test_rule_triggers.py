"""One input per rule that must make it fire, and the check that none is missing.

**This file was written to close a hole that mostly was not there,** and the correction is worth
recording because the reasoning that produced it looked sound.

The observation was real: of thirty rule classes, only *six* ever produce a violation on either
corpus document. The other twenty-four are checked on every build and permanently silent,
because the output is good. From that I concluded most of the suite was unprotected -- a rule
that stopped working would look exactly like a rule that passed.

Then I measured it properly, with ``tools/mutate_rules.py``: gut one rule's ``check()`` at a
time and see whether anything fails. **Twenty-nine of thirty were already caught**, by broken-
input tables scattered across ``test_triage_and_lint.py``, ``test_script_lint.py`` and
``test_artefact_lint.py``. Silence on good documents says nothing about coverage, and I had
read it as if it did.

One rule was genuinely unprotected -- ``STR-08``, dangling references -- and it is also the only
rule id that appears in no other test file, which is the cheap signal that would have found it.

So what this file is actually for is the *second* test, not the first:

- :func:`test_every_rule_has_a_trigger` enumerates the rule classes by reflection and fails when
  one has no entry. Nothing before this made a new rule prove it can speak, and the existing
  tables cannot: they are lists someone has to remember to extend. This is the part that matters
  going forward, and it matters most for rules a model drafts, where "it type-checks and the
  suite is green" is not evidence of anything.
- :func:`test_every_trigger_fires` runs each rule against its own trigger. Mostly redundant with
  what the scattered tables already do; kept because it is what gives the first test something
  to enforce, and because one place to look beats three.

The inputs are minimal on purpose. A trigger built by breaking a real document fires for reasons
that are hard to see, and keeps firing after the rule is gutted, because a real document breaks
several rules at once.
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable
from typing import Any

import pytest

from mimem.config import Profile
from mimem.ir import (
    Analogy,
    Anchor,
    Beat,
    BeatType,
    Block,
    BlockKind,
    BlockRole,
    Card,
    Concept,
    Document,
    Script,
    Section,
    Segment,
    SourceMeta,
    Span,
)
from mimem.lint.artefact_rules import ArtefactRule, Bundle
from mimem.lint.rules import LintRule
from mimem.lint.script_rules import ScriptRule

# -- builders --------------------------------------------------------------------------------


def _beat(
    beat_id: str,
    beat_type: BeatType = BeatType.EXPOSITION,
    text: str = "A sentence from the paper.",
    **kwargs: Any,
) -> Beat:
    kwargs.setdefault("spans", [Span(block_id="b1", char_start=0, char_end=10, page=1)])
    kwargs.setdefault("est_seconds", 5.0)
    return Beat(id=beat_id, type=beat_type, text=text, **kwargs)


def _script(
    *,
    opening: list[Beat] | None = None,
    segments: list[list[Beat]] | None = None,
    review: list[Beat] | None = None,
    cards: list[Card] | None = None,
    registry: dict[str, Concept] | None = None,
    title: str = "A section",
) -> Script:
    sections = []
    if segments:
        sections = [
            Section(
                id="sec1",
                title=title,
                segments=[
                    Segment(id=f"seg{i}", section_id="sec1", beats=beats)
                    for i, beats in enumerate(segments)
                ],
            )
        ]
    return Script(
        doc_id="doc1",
        source=SourceMeta(format="markdown"),
        profile="study",
        opening=opening or [],
        sections=sections,
        review=review or [],
        cards=cards or [],
        registry=registry or {},
    )


def _concept(concept_id: str = "c1", canonical: str = "reference resonator", **kw: Any) -> Concept:
    return Concept(id=concept_id, canonical=canonical, **kw)


def _doc(blocks: list[Block] | None = None) -> Document:
    return Document(
        id="doc1",
        source=SourceMeta(format="markdown"),
        blocks=blocks
        or [Block(id="b1", kind=BlockKind.PARAGRAPH, role=BlockRole.INTRODUCTION, text="Text.")],
    )


def _two_section_script() -> Script:
    """One concept met in two adjacent sections, closer than the minimum gap.

    Getting this to fire needs the gap in a window, which is itself worth recording. Two
    exposures inside one section are a single episode by design -- the spacing clock starts at
    the section boundary -- so the trigger has to cross one. And any two exposures within sixty
    seconds coalesce whatever section they are in, so they also have to be *further* apart than
    that. The gap therefore has to sit between the episode window (60 s) and the minimum gap
    (180 s), which is why the first section carries two minutes of filler.
    """

    def section(index: str, beats: list[Beat]) -> Section:
        return Section(
            id=f"sec{index}",
            title=f"Section {index}",
            segments=[Segment(id=f"seg{index}", section_id=f"sec{index}", beats=beats)],
        )

    return Script(
        doc_id="doc1",
        source=SourceMeta(format="markdown"),
        profile="study",
        sections=[
            section(
                "1",
                [
                    _beat("e1", concept_ids=["c1"], text="The reference resonator is introduced."),
                    _beat(
                        "f1",
                        text="Filler that carries the clock past the episode window.",
                        est_seconds=120.0,
                    ),
                ],
            ),
            section(
                "2",
                [
                    _beat(
                        "cb1",
                        BeatType.CALLBACK,
                        "Back to the reference resonator.",
                        concept_ids=["c1"],
                        est_seconds=5.0,
                    )
                ],
            ),
        ],
        registry={"c1": _concept()},
    )


# -- the triggers ----------------------------------------------------------------------------
#
# Each entry is a callable returning the input that rule should fire on. Text rules take a
# string, script rules a Script, artefact rules a Bundle -- keyed by rule id, so the reflection
# test can match them against the classes it finds.

TEXT_TRIGGERS: dict[str, Callable[[], str]] = {
    "CIT-01": lambda: "The layer passivates the surface, as Peled et al. showed.",
    "NUM-02": lambda: "The drift coefficient fell to 0.0031 percent per kelvin.",
    "SENT-01": lambda: "This " + "very " * 40 + "long sentence never stops.",
    "SENT-03": lambda: "The residual (see the discussion) is dominated by clamping stress.",
    "SENT-04": lambda: "The devices were cycled e.g. between two temperatures.",
    "STR-08": lambda: "As shown in the figure, the residual rises with clamping stress.",
    "SYM-02": lambda: "The SEI limits further reduction of the electrolyte.",
    "TTS-01": lambda: "The gap is ~5 §, which the reader will notice.",
}

SCRIPT_TRIGGERS: dict[str, Callable[[], Script]] = {
    # A card exists, so two to four prequestions are required; none are asked.
    "STR-02": lambda: _script(
        cards=[
            Card(
                id="card1",
                subject="clamping stress",
                prompt="What sets the floor?",
                answer="Clamping stress.",
            )
        ],
        segments=[[_beat("e1")]],
    ),
    # A section with neither a recap nor a prompt.
    "STR-06": lambda: _script(segments=[[_beat("e1"), _beat("e2")]]),
    # Two consecutive review items from the same section.
    "STR-07": lambda: _script(
        cards=[
            Card(id="card1", subject="one", prompt="Q1?", answer="A1.", section_id="sec1"),
            Card(id="card2", subject="two", prompt="Q2?", answer="A2.", section_id="sec1"),
        ],
        review=[
            _beat("rv1", BeatType.PROMPT, "Q1?", card_id="card1", generated=True, spans=[]),
            _beat("rv2", BeatType.PROMPT, "Q2?", card_id="card2", generated=True, spans=[]),
        ],
    ),
    # One segment far past the hard maximum.
    "SEG-01": lambda: _script(segments=[[_beat("e1", est_seconds=600.0)]]),
    # More new concepts in one segment than the budget allows.
    "SEG-03": lambda: _script(
        segments=[
            [
                _beat(f"e{i}", concept_ids=[f"c{i}"], text=f"Concept {i} is introduced here.")
                for i in range(8)
            ]
        ],
        registry={f"c{i}": _concept(f"c{i}", f"term {i}") for i in range(8)},
    ),
    # A prompt with no answer after it.
    "RET-01": lambda: _script(
        segments=[
            [
                _beat(
                    "p1",
                    BeatType.PROMPT,
                    "What sets the floor?",
                    generated=True,
                    spans=[],
                    pause_after=8.0,
                )
            ]
        ]
    ),
    # A prompt with no thinking time.
    "PAU-01": lambda: _script(
        segments=[
            [
                _beat(
                    "p1",
                    BeatType.PROMPT,
                    "What sets it?",
                    generated=True,
                    spans=[],
                    pause_after=0.0,
                ),
                _beat("a1", BeatType.ANSWER, "The stress."),
            ]
        ]
    ),
    # An anchor with no pause after it.
    "PAU-02": lambda: _script(
        segments=[
            [
                _beat(
                    "an1",
                    BeatType.ANCHOR,
                    "Picture a tuning fork.",
                    generated=True,
                    spans=[],
                    pause_after=0.0,
                )
            ]
        ]
    ),
    # The same concept said twice in the same words.
    "REP-01": lambda: _script(
        segments=[
            [
                _beat(
                    "e1",
                    concept_ids=["c1"],
                    text="The reference resonator is held free at one end.",
                ),
                _beat(
                    "cb1",
                    BeatType.CALLBACK,
                    "The reference resonator is held free at one end.",
                    concept_ids=["c1"],
                ),
            ]
        ],
        registry={"c1": _concept()},
    ),
    # Two scheduled callbacks a few seconds apart.
    "SPC-01": lambda: _two_section_script(),
    # A beat that makes a claim about the paper and cannot point at it.
    "GRD-01": lambda: _script(segments=[[_beat("e1", spans=[])]]),
    # Two concepts given the same anchor.
    "IMG-02": lambda: _script(
        segments=[[_beat("e1")]],
        registry={
            "c1": _concept("c1", "first term", anchor=Anchor(text="Picture a tuning fork.")),
            "c2": _concept("c2", "second term", anchor=Anchor(text="Picture a tuning fork.")),
        },
    ),
    # An analogy that never says where it breaks down.
    "ANA-01": lambda: _script(
        segments=[[_beat("e1")]],
        registry={
            "c1": _concept(
                "c1",
                "drift",
                # Not an *empty* limit: the `Analogy` model rejects that itself, so the rule's
                # empty-limit branch cannot be reached through a constructed script at all. The
                # reachable half is a limit that just restates the analogy.
                analogy=Analogy(
                    text="Like a clock left in the sun, the resonator runs fast when warm.",
                    limit="Like a clock left in the sun, the resonator runs fast when warm.",
                ),
            )
        },
    ),
    # Our own scaffolding, not marked as ours.
    "VOI-02": lambda: _script(
        segments=[[_beat("an2", BeatType.ANCHOR, "Think of the die as a warming plate.", spans=[])]]
    ),
    # A written number the source sentences never state.
    "GRD-03": lambda: _script(
        segments=[
            [
                _beat(
                    "g1",
                    BeatType.GLOSS,
                    "Compensation increases the residual drift coefficient.",
                    written_text="Compensation decreases the residual drift coefficient.",
                )
            ]
        ]
    ),
    # A chunk that stops mid-sentence.
    "TTS-04": lambda: _script(segments=[[_beat("e1", text="The residual drift is dominated by")]]),
    # A beat opening on a pronoun with no referent in it.
    "SENT-02": lambda: _script(
        segments=[
            [
                _beat("e1", text="The clamping stress differs between the two resonators."),
                _beat(
                    "e2",
                    text="This is what sets the floor on paired compensation.",
                    generated=False,
                ),
            ]
        ]
    ),
    # A table read out before the listener is told it is a table.
    "TBL-02": lambda: _script(
        segments=[
            [
                _beat(
                    "tb1",
                    BeatType.TABLE,
                    "Measurement resonator, zero point zero one four two. Reference, zero point zero one three eight.",
                )
            ]
        ]
    ),
    # A figure description that never says what kind of figure it is.
    "FIG-01": lambda: _script(
        segments=[
            [
                _beat(
                    "fg1",
                    BeatType.FIGURE,
                    "The residual rises steadily across the measured range, with two devices "
                    "falling well below the trend, both of which had visible die-attach voids "
                    "that the authors identified after the fact.",
                )
            ]
        ]
    ),
    # Two questions answered by the same sentence. Not the review block re-asking, which is
    # what STR-07 wants: these are two distinct cards.
    "RET-06": lambda: _script(
        segments=[[_beat("e1")]],
        cards=[
            Card(
                id="card1",
                subject="reference resonator",
                prompt="What did they report for the reference resonator?",
                answer="Here's the answer about reference resonator. It cuts drift by most of it.",
            ),
            Card(
                id="card2",
                subject="resonant strain sensor",
                prompt="What did they report for the resonant strain sensor?",
                answer=(
                    "Here's the answer about resonant strain sensor. It cuts drift by most of it."
                ),
            ),
        ],
    ),
    # A transition that announces one concept, followed by beats about another. Real: four of
    # six transitions in one programme did this, because the planner chose from every concept
    # anywhere in the next segment rather than from its opening.
    "SEG-04": lambda: _script(
        segments=[
            [
                _beat(
                    "t1",
                    BeatType.TRANSITION,
                    "More on the measurement resonator.",
                    concept_ids=["c1"],
                    generated=True,
                    spans=[],
                ),
                _beat("e1", concept_ids=["c2"], text="Something else entirely."),
            ]
        ],
        registry={
            "c1": _concept("c1", "measurement resonator"),
            "c2": _concept("c2", "clamping stress"),
        },
    ),
}

ARTEFACT_TRIGGERS: dict[str, Callable[[], Bundle]] = {
    # An acknowledgement triage dropped, showing up in the audio track anyway.
    "COH-01": lambda: Bundle(
        script=_script(segments=[[_beat("e1")]]),
        doc=_doc(
            [
                Block(
                    id="b1",
                    kind=BlockKind.PARAGRAPH,
                    role=BlockRole.ACKNOWLEDGEMENT,
                    text="We thank the Westmere cleanroom staff for performing the release etch.",
                )
            ]
        ),
        audio="We thank the Westmere cleanroom staff for performing the release etch.",
        study="",
    ),
    # An equation in the source that the written companion never reproduces.
    "MTH-04": lambda: Bundle(
        script=_script(segments=[[_beat("e1")]]),
        doc=_doc(
            [
                Block(
                    id="b1",
                    kind=BlockKind.EQUATION,
                    role=BlockRole.METHODS,
                    text="alpha = (1/f)(df/dT)",
                )
            ]
        ),
        audio="",
        study="Nothing about any equation at all.",
    ),
    # An exact value in the source that never reaches study.md.
    "NUM-06": lambda: Bundle(
        script=_script(
            segments=[
                [
                    _beat(
                        "e1",
                        text="The residual drift coefficient fell sharply across the batch.",
                        spans=[Span(block_id="b1", char_start=0, char_end=71, page=1)],
                    )
                ]
            ]
        ),
        doc=_doc(
            [
                Block(
                    id="b1",
                    kind=BlockKind.PARAGRAPH,
                    role=BlockRole.RESULTS,
                    text="The residual drift coefficient fell to 0.0031 %/K across forty devices.",
                )
            ]
        ),
        audio="",
        study="The residual drift fell by a lot.",
    ),
}


# -- the tests -------------------------------------------------------------------------------

_MODULES = (
    ("mimem.lint.rules", LintRule),
    ("mimem.lint.script_rules", ScriptRule),
    ("mimem.lint.artefact_rules", ArtefactRule),
)


def _rule_classes() -> list[type]:
    """Every concrete rule, found by reflection rather than by a list anyone has to maintain."""
    found: list[type] = []
    for name, base in _MODULES:
        # The module name is shadowed by a same-named function in the package __init__, so this
        # has to go through importlib: `from mimem.lint import script_rules` gets the function.
        module = importlib.import_module(name)
        found.extend(
            obj
            for _, obj in inspect.getmembers(module, inspect.isclass)
            if issubclass(obj, base)
            and obj is not base
            and not inspect.isabstract(obj)
            and getattr(obj, "id", None)
        )
    return sorted(found, key=lambda c: c.id)


def _trigger_for(rule: type) -> Callable[[], Any] | None:
    for table in (TEXT_TRIGGERS, SCRIPT_TRIGGERS, ARTEFACT_TRIGGERS):
        if rule.id in table:
            return table[rule.id]
    return None


def test_every_rule_has_a_trigger() -> None:
    """A rule with nothing that makes it fire cannot be shown to work.

    This is the test that keeps the set complete: add a rule, and it fails until you have
    written the broken input that proves the rule can speak.
    """
    missing = sorted(r.id for r in _rule_classes() if _trigger_for(r) is None)
    assert not missing, f"no trigger for: {', '.join(missing)}"


def test_no_trigger_is_orphaned() -> None:
    """...and the other direction, so a deleted rule does not leave a trigger behind."""
    known = {r.id for r in _rule_classes()}
    triggers = set(TEXT_TRIGGERS) | set(SCRIPT_TRIGGERS) | set(ARTEFACT_TRIGGERS)
    assert not (triggers - known), f"trigger for a rule that no longer exists: {triggers - known}"


@pytest.mark.parametrize("rule_class", _rule_classes(), ids=lambda c: str(c.id))
def test_every_trigger_fires(rule_class: type) -> None:
    """The point of the whole file: each rule, given its own broken input, says so."""
    trigger = _trigger_for(rule_class)
    assert trigger is not None, f"{rule_class.id} has no trigger"

    rule = rule_class() if rule_class.id in TEXT_TRIGGERS else rule_class(Profile(name="study"))
    violations = rule.check(trigger())

    assert violations, f"{rule_class.id} ({rule_class.__name__}) did not fire on its own trigger"
    assert all(v.rule == rule_class.id for v in violations)


def test_the_rule_count_is_what_the_docs_claim() -> None:
    """The README says the count; if that changes, the sentence changes with it."""
    assert len(_rule_classes()) == 32


def test_every_rule_is_registered() -> None:
    """A rule the linter never calls is a rule that does not exist.

    The gap this closes was found by falling into it. Two rules were written, given triggers
    above, and covered by `test_every_trigger_fires` -- and never ran, because the linter calls
    a hand-maintained tuple and that tuple sat *above* the classes in the file. Every test here
    passed. `mimem build` checked thirty rules and reported thirty.

    Enumerating classes and enumerating the registry are different questions, and the first one
    reassured me about the second. It is the same drift as the extension manifest listing ten
    tools while the server answered eleven.
    """
    from mimem.lint.artefact_rules import artefact_rules
    from mimem.lint.rules import DEFAULT_RULES
    from mimem.lint.script_rules import script_rules

    registered = {
        rule.id for group in (DEFAULT_RULES, script_rules(), artefact_rules()) for rule in group
    }
    defined = {cls.id for cls in _rule_classes()}
    assert defined == registered, f"defined but never run: {sorted(defined - registered)}"
