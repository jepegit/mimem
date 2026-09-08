"""Stage 6: the elaboration layer, its safety rails, and the worked example.

Three groups. The first checks that nothing here is trusted because it is fluent: a task whose
output states a number the source does not is rejected, not stored. The second checks that every
task has a way to fail that leaves a working programme behind, because "one bad figure must not
kill a three-hundred-page book" is a design commitment and not a hope. The third is the
milestone's acceptance criterion: the target rendering in ``docs/examples/sample-output.md``,
produced end to end from the source paragraph in the same document.

The answers here are scripted rather than recorded from a model. That is deliberate and it is
what these tests are for -- they check the plumbing, the grounding gate and the beat structure,
none of which should depend on what a model happens to say on a given day. What a model actually
says is a question for the evaluation harness in M6.
"""

from __future__ import annotations

import pytest

# `SOURCE_PARAGRAPH`, `CONTEXT`, `ANSWERS`, `_doc`, `sample_doc` and `study` moved to
# tests/conftest.py when a second module needed them.
from worked_example import ANSWERS  # type: ignore[import-not-found]

from mimem.concepts import build as build_registry
from mimem.config import Listener, Profile, load_profile
from mimem.elaborate import elaborate, plan_requests
from mimem.ir import (
    BeatType,
    Document,
)
from mimem.lint import lint_script
from mimem.llm import NullClient, ScriptedClient
from mimem.llm.cost import BudgetExceededError
from mimem.plan import plan
from mimem.render import render_audio, render_study


@pytest.fixture
def drill() -> Profile:
    """The worked example is a dense rendering: about two and a half minutes for one paragraph.

    Under ``study`` the duration budget is 1.4x the straight read of the content, and on a single
    paragraph the fixed scaffolding -- orientation, prequestions, pre-load, recap, question --
    eats all of it, so rule DUR-02 cuts the analogy first exactly as it is supposed to. The
    density in ``sample-output.md`` is what ``drill`` buys, and asking for it under ``study``
    would be asking the budget rule to make an exception for a document.
    """
    return load_profile("drill")


# -- the grounding gate ------------------------------------------------------------------------


def test_an_invented_number_is_rejected_not_stored(sample_doc: Document, study: Profile) -> None:
    """Rule GRD-03, and the milestone's other acceptance criterion.

    The elaboration reads well and states a number the paper never gives. Fluency is exactly why
    this needs a mechanical check: nothing about the sentence sounds wrong.
    """
    registry = build_registry(sample_doc, Listener())
    corrupted = {
        "gloss": [
            {
                "short_def": "the crust on the negative electrode",
                "long_def": "It costs 41.85 percent of capacity over the run.",
                "spoken": None,
            }
        ]
    }
    report = elaborate(
        sample_doc,
        registry,
        study,
        Listener(),
        ScriptedClient(corrupted),  # type: ignore[arg-type]
    )
    assert report.rejected, "the grounding check let an invented number through"
    assert any(f.kind == "number" and f.value == "41.85" for f in report.rejected)
    assert all(c.long_def is None for c in registry.concepts.values())


def test_a_flipped_direction_is_rejected(sample_doc: Document, study: Profile) -> None:
    registry = build_registry(sample_doc, Listener())
    flipped = {
        "why": [{"text": "The thickness of the interphase decreases over the first cycles."}]
    }
    report = elaborate(
        sample_doc,
        registry,
        study,
        Listener(),
        ScriptedClient(flipped),  # type: ignore[arg-type]
    )
    assert all(c.why is None for c in registry.concepts.values())
    assert report.degraded


def test_a_faithful_elaboration_is_kept(sample_doc: Document, study: Profile) -> None:
    registry = build_registry(sample_doc, Listener())
    report = elaborate(
        sample_doc,
        registry,
        study,
        Listener(),
        ScriptedClient(dict(ANSWERS)),  # type: ignore[arg-type]
    )
    assert report.succeeded
    assert any(c.long_def for c in registry.concepts.values())


# -- degradation -------------------------------------------------------------------------------


def test_no_model_means_a_smaller_programme_not_a_failed_build(
    sample_doc: Document, study: Profile
) -> None:
    """``--local``: nothing is attempted, the report says why once, and the plan still builds.

    This used to assert `report.degraded`, because every task attempted a call, failed with the
    same "no model configured" and recorded its own degradation. Forty identical lines is how a
    single missing key came to look like forty separate problems, so a run with no provider now
    sets every task to `off` and says so once.
    """
    registry = build_registry(sample_doc, Listener())
    report = elaborate(sample_doc, registry, study, Listener(), NullClient())

    assert report.no_provider
    assert not report.degraded, "no provider is one fact, not one per task"
    assert not report.succeeded
    assert "no model configured" in report.summary()

    script = plan(sample_doc, registry, study, Listener())
    assert script.beats()
    assert not any(b.type is BeatType.ANCHOR for b in script.beats())


def test_a_gloss_falls_back_to_the_papers_own_definition(
    sample_doc: Document, study: Profile
) -> None:
    """Rule PRE-01 still needs a line for the pre-load when the model is unavailable."""
    registry = build_registry(sample_doc, Listener())
    elaborate(sample_doc, registry, study, Listener(), NullClient())
    assert any(c.short_def for c in registry.concepts.values())


def test_a_partial_failure_keeps_what_worked(sample_doc: Document, study: Profile) -> None:
    """One task failing must not lose the tasks that succeeded."""
    registry = build_registry(sample_doc, Listener())
    partial = {"gloss": list(ANSWERS["gloss"])}  # anchors, whys and analogies all fail
    report = elaborate(
        sample_doc,
        registry,
        study,
        Listener(),
        ScriptedClient(partial),  # type: ignore[arg-type]
    )
    assert report.succeeded.get("gloss")
    assert report.degraded


def test_the_budget_cap_stops_before_spending(sample_doc: Document, study: Profile) -> None:
    registry = build_registry(sample_doc, Listener())
    with pytest.raises(BudgetExceededError):
        elaborate(
            sample_doc,
            registry,
            study,
            Listener(),
            ScriptedClient(dict(ANSWERS)),  # type: ignore[arg-type]
            budget=0.0000001,
        )


def test_a_dry_run_makes_no_calls(sample_doc: Document, study: Profile) -> None:
    registry = build_registry(sample_doc, Listener())
    planned = plan_requests(sample_doc, registry, study, Listener())
    assert planned.requests
    assert planned.total() > 0
    assert "estimate, not a quote" in planned.report()


# -- the worked example ------------------------------------------------------------------------


@pytest.fixture
def elaborated(sample_doc: Document, drill: Profile):
    registry = build_registry(sample_doc, Listener())
    elaborate(
        sample_doc,
        registry,
        drill,
        Listener(),
        ScriptedClient(dict(ANSWERS)),  # type: ignore[arg-type]
    )
    return plan(sample_doc, registry, drill, Listener())


def test_the_programme_contains_what_the_worked_example_promises(elaborated) -> None:
    """The M5 acceptance criterion, against ``docs/examples/sample-output.md`` section E."""
    types = {b.type for b in elaborated.beats()}
    assert BeatType.GLOSS in types
    assert BeatType.ANCHOR in types
    assert BeatType.ANALOGY in types
    assert BeatType.PROMPT in types
    assert BeatType.PREQUESTION in types


def test_the_anchor_and_the_analogy_are_marked_as_ours(elaborated) -> None:
    """Section E, point 3: rules ANA-01 and VOI-02."""
    anchor = next(b for b in elaborated.beats() if b.type is BeatType.ANCHOR)
    analogy = next(b for b in elaborated.beats() if b.type is BeatType.ANALOGY)
    assert "way to picture it" in anchor.text
    assert "my analogy, not theirs" in analogy.text.lower()
    assert "breaks down" in analogy.text
    assert anchor.pause_after >= 2.0  # rule PAU-02


def test_the_gloss_points_at_the_source_and_the_anchor_does_not(elaborated) -> None:
    """Rule GRD-01: a gloss makes claims about the paper; an anchor is ours."""
    gloss = next(b for b in elaborated.beats() if b.type is BeatType.GLOSS)
    anchor = next(b for b in elaborated.beats() if b.type is BeatType.ANCHOR)
    assert gloss.spans
    assert not anchor.spans
    assert anchor.generated and anchor.provenance is not None


def test_the_exact_values_survive_in_the_written_track(elaborated) -> None:
    """Section E, point 2, and rule NUM-06."""
    audio = render_audio(elaborated)
    study_text = render_study(elaborated)
    assert "0.0837" not in audio
    assert "zero point zero eight, three seven" in audio  # NUM-01b: chunked, not a digit run
    assert "0.0837" in study_text


def test_the_elaborated_programme_lints_clean(elaborated, drill: Profile) -> None:
    report = lint_script(elaborated, profile=drill)
    assert report.ok, (
        report.summary() + "\n" + "\n".join(f"{v.rule}: {v.message}" for v in report.errors[:10])
    )


# -- the gate on schemas it was not written for -------------------------------------------------


def test_the_gate_covers_a_schema_with_no_text_field() -> None:
    """The gate used to read a field called ``text`` and check the empty string when there was
    none. ``FigureOut`` has six fields and none of them is ``text``, so figure descriptions --
    the highest-hallucination-risk output in the system -- were the one output nothing checked.

    A pie-chart description claiming hydrogen "climbs from 12.4 percent to 51.8 percent", both
    numbers invented, passed the gate cleanly.
    """
    from mimem.elaborate.run import ground
    from mimem.llm.schemas import FigureOut

    invented = FigureOut(
        statement="Hydrogen rises across the samples",
        kind="four pie charts",
        axes="share of total gas volume as a percentage",
        trend="Hydrogen climbs from 12.4 percent in the first sample to 51.8 percent in the last.",
        exceptions="None.",
        claim="Hydrogen share increases with nickel content.",
        confidence=0.9,
    )
    findings = ground(invented, "Gas production composition and volume percentage of four samples.")
    assert {f.value for f in findings} == {"12.4", "51.8"}


def test_a_figure_description_may_not_quote_a_value_the_paper_never_wrote() -> None:
    """The rule that falls out of the gate, rather than one imposed on it.

    Numbers read off a plot are in the *image*, and a text gate cannot tell them from invented
    ones -- so it rejects a correct description and a fabricated one alike. That is not a gate
    failure, it is the specification: a figure description says "well over half", and the exact
    value stays in study.md and on the crop, where a reader can check it against the picture.
    """
    from mimem.elaborate.run import ground
    from mimem.llm.schemas import FigureOut

    source = "Gas production composition and volume percentage of four samples."
    common = {
        "statement": "Gas composition differs sharply between the four chemistries",
        "kind": "four pie charts, one per sample",
        "axes": "share of total gas volume as a percentage",
        "exceptions": "The fourth sample's largest share belongs to a different gas.",
        "claim": "Composition is a fingerprint of the chemistry.",
        "confidence": 0.8,
    }
    read_off_the_plot = FigureOut(
        trend="One gas takes 60.27 percent of the third sample.", **common
    )
    qualitative = FigureOut(
        trend="One gas takes well over half of the third sample on its own.", **common
    )

    assert ground(read_off_the_plot, source), "a value only the image states is not verifiable"
    assert ground(qualitative, source) == []
