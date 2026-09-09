"""Stage 6 splitting the source's long sentences (rule SENT-01).

The design rule is *long source sentences are split, not compressed*, and these tests are
mostly about the difference. A summary of a sentence reads exactly like a split of it, so the
prose cannot tell them apart and the check has to: a split is lossless, so every number has to
survive in **both** directions, and that asymmetry is the only reason this is safe to do to a
paper's own words.

The answers are scripted rather than recorded, for the reason ``test_elaborate`` gives: these
check the plumbing and the gate, neither of which should depend on what a model says today.
"""

from __future__ import annotations

import pytest

from mimem.config import Listener, load_profile
from mimem.elaborate import elaborate
from mimem.elaborate.sentences import MAX_GROWTH, over_long, verify_split
from mimem.ir import Block, BlockKind, BlockRole, Document, SourceMeta, TriageAction
from mimem.ir.models import TriageDecision
from mimem.llm import NullClient, ScriptedClient

LONG = (
    "The reversible capacity of the electrodes cycled in the fluoroethylene carbonate "
    "electrolyte was 3867.3 mAh/g after the first cycle, which is higher than the 252 mAh/g "
    "measured for the electrodes cycled in the ethylene carbonate electrolyte under otherwise "
    "identical conditions at a rate of 0.1 C."
)

SPLIT = [
    "The electrodes cycled in the fluoroethylene carbonate electrolyte had a reversible "
    "capacity of 3867.3 mAh/g after the first cycle.",
    "That is higher than the 252 mAh/g measured for the electrodes cycled in the ethylene "
    "carbonate electrolyte at a rate of 0.1 C.",
]


def _doc(text: str = LONG) -> Document:
    from mimem.clean import sentence_spans

    block = Block(
        id="b1",
        kind=BlockKind.PARAGRAPH,
        role=BlockRole.BODY,
        text=text,
        page=1,
        order=0,
        sentences=sentence_spans(text),
        triage=TriageDecision(action=TriageAction.KEEP, rule="COH-04", reason="carries it"),
    )
    return Document(id="d", source=SourceMeta(format="pdf"), blocks=[block])


# -- what counts as too long --------------------------------------------------------------------


def test_length_is_counted_on_what_the_listener_hears() -> None:
    """ "298 K" is two words written and four spoken, and the listener gets the spoken one.

    Selecting on the written form misses the sentences that are long *because of what they
    state*, which are the ones a listener most needs split.
    """
    profile = load_profile("study")
    written = "The cell was held at 298 K and 3867.3 mAh/g was measured at 0.1 C afterwards."
    assert len(written.split()) < 20
    found = over_long(_doc(written), profile, Listener(), cap=20)
    assert found and found[0].spoken_words > 20


def test_a_short_sentence_is_left_alone() -> None:
    found = over_long(_doc("The cell failed early."), load_profile("study"), Listener())
    assert found == []


def test_a_table_has_no_sentences_to_split() -> None:
    """Its caption speaks for it, and its words are not prose."""
    doc = _doc()
    doc.blocks[0].kind = BlockKind.TABLE
    assert over_long(doc, load_profile("study"), Listener()) == []


def test_a_dropped_block_is_not_worth_splitting() -> None:
    doc = _doc()
    doc.blocks[0].triage = TriageDecision(
        action=TriageAction.DROP, rule="COH-01", reason="back matter"
    )
    assert over_long(doc, load_profile("study"), Listener()) == []


# -- the check that separates a split from a summary ---------------------------------------------


def test_a_faithful_split_passes() -> None:
    assert verify_split(LONG, SPLIT, cap=25) == []


def test_a_summary_is_caught_by_the_numbers_it_drops() -> None:
    """The check no other task in stage 6 can fail, and the reason this one is safe.

    Everything else here writes new text and can only be asked whether it invented something. A
    summary invents nothing -- it just quietly stops saying four of the paper's measurements.
    """
    summary = [
        "The capacity was much higher in the fluoroethylene carbonate electrolyte.",
        "The ethylene carbonate electrolyte performed worse.",
    ]
    dropped = {f.value for f in verify_split(LONG, summary, cap=25) if f.kind == "number"}
    assert {"3867.3", "252", "0.1"} <= dropped


def test_a_flipped_comparison_is_caught() -> None:
    """ "higher" for "lower" is the worst thing this system can produce, and it reads perfectly."""
    flipped = [SPLIT[0], SPLIT[1].replace("higher", "lower")]
    findings = verify_split(LONG, flipped, cap=25)
    assert any(f.kind == "direction" for f in findings)


def test_an_invented_number_is_caught() -> None:
    invented = [SPLIT[0], SPLIT[1] + " A third cell reached 99 mAh/g."]
    assert any(f.value == "99" for f in verify_split(LONG, invented, cap=25))


def test_one_sentence_back_is_not_a_split() -> None:
    assert any(f.kind == "split" for f in verify_split(LONG, [LONG], cap=25))


def test_sentences_still_over_the_cap_have_not_done_the_job() -> None:
    findings = verify_split(LONG, [LONG[:200], LONG[200:]], cap=5)
    assert any("cap" in f.message for f in findings)


def test_an_expansion_is_not_a_split() -> None:
    """Growth is expected -- a repeated subject costs words -- and half as much again is not."""
    padded = [SPLIT[0], SPLIT[1], " ".join(["and the cells were then rested"] * 12)]
    findings = verify_split(LONG, padded, cap=60)
    assert any("expansion" in f.message for f in findings)
    assert MAX_GROWTH < 2


# -- the stage ------------------------------------------------------------------------------------


def _elaborate(doc: Document, answers: dict[str, list[dict[str, object]]]):
    registry_profile = load_profile("study")
    from mimem.concepts import build as build_registry

    return elaborate(
        doc,
        build_registry(doc, Listener()),
        registry_profile,
        Listener(),
        ScriptedClient(answers),
    )


def test_the_split_is_stored_beside_the_sentence_and_the_source_is_not_touched() -> None:
    doc = _doc()
    before = doc.blocks[0].text
    report = _elaborate(doc, {"split": [{"sentences": SPLIT}]})

    block = doc.blocks[0]
    assert block.text == before, "the paper's own words were edited"
    assert block.rewrites, "the split was not stored"
    start, end = block.sentences[0]
    assert block.spoken_text(start, end) == " ".join(SPLIT)
    assert report.succeeded.get("split") == 1


def test_a_summary_is_rejected_and_the_source_sentence_survives() -> None:
    doc = _doc()
    summary = ["The capacity was higher with the additive.", "Both cells were tested."]
    report = _elaborate(doc, {"split": [{"sentences": summary}]})

    assert doc.blocks[0].rewrites == {}
    assert report.rejected, "a summary passed the gate"
    assert any(d.task == "split" for d in report.degraded)


def test_no_model_means_the_sentence_is_left_long() -> None:
    """The control path. The linter goes on reporting it, which is the honest outcome."""
    doc = _doc()
    from mimem.concepts import build as build_registry

    report = elaborate(
        doc, build_registry(doc, Listener()), load_profile("study"), Listener(), NullClient()
    )
    assert doc.blocks[0].rewrites == {}
    assert report.no_provider


def test_the_planner_speaks_the_split_and_still_points_at_the_source() -> None:
    """Rule GRD-02 checks a beat against its spans, so the span has to stay on what was written."""
    from mimem.concepts import build as build_registry
    from mimem.ir import BeatType
    from mimem.plan import plan

    doc = _doc()
    _elaborate(doc, {"split": [{"sentences": SPLIT}]})
    script = plan(doc, build_registry(doc, Listener()), load_profile("study"), Listener())

    exposition = [b for b in script.beats() if b.type is BeatType.EXPOSITION]
    assert exposition, "the fixture produced no exposition"
    said = " ".join(b.text for b in exposition)
    assert "That is higher than" in said, "the split was not spoken"
    for beat in exposition:
        for span in beat.spans:
            assert doc.text_of(span) in doc.blocks[0].text


@pytest.mark.parametrize("cap", [25])
def test_the_split_cap_leaves_room_for_the_verbalizer(cap: int) -> None:
    """Asked for twenty-five, checked at thirty-five, because numbers are not spoken yet.

    A sentence split to exactly the linter's cap in *written* words is over it by the time its
    numbers have been said, which would spend a model call and change nothing.
    """
    from mimem.elaborate.run import SPLIT_CAP
    from mimem.lint.rules import SentenceLength

    assert SPLIT_CAP == cap < SentenceLength.HARD_CAP
