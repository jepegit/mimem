"""One passing and one failing example for every structural lint rule.

The plan under test has been through stage 6 -- it has a gloss, an anchor, an analogy and a
why-explanation on its top concept -- because three of these rules have nothing to look at
otherwise, and a rule that passes because the artefact is empty has not been tested.

The plan asks for a pass/fail fixture pair per rule, and this is that, built as mutations rather
than as JSON files on disk. A mutation says what the rule is *about* -- "delete the answer beat",
"give two concepts the same anchor" -- in a way a hand-written fixture does not, and it cannot
drift out of date as the script model changes, because it is derived from a real plan every time.

Each case asserts both directions. A rule that fires on the mutation but also fires on the clean
plan is not a rule, it is noise; a rule that stays silent on both is decoration.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from mimem.config import Profile
from mimem.ir import Analogy, Anchor, Beat, BeatType, Script, Span, beat_id
from mimem.lint.rules import Severity
from mimem.lint.script_rules import ScriptRule, script_rules

Mutator = Callable[[Script], None]


def _rule(rule_id: str, profile: Profile) -> ScriptRule:
    return next(r for r in script_rules(profile) if r.id == rule_id)


def _errors(rule: ScriptRule, script: Script) -> list[str]:
    return [v.message for v in rule.check(script) if v.severity is Severity.ERROR]


# -- the mutations ----------------------------------------------------------------------------


def _break_prequestions(script: Script) -> None:
    """STR-02: a prequestion that is not in the card pool."""
    for beat in script.opening:
        if beat.type is BeatType.PREQUESTION and beat.card_id:
            beat.card_id = "k_invented"
            return
    raise AssertionError("the fixture has no prequestion to break")


def _remove_recaps(script: Script) -> None:
    """STR-06: a section that never sums itself up."""
    for segment in script.sections[0].segments:
        segment.beats = [b for b in segment.beats if b.type is not BeatType.RECAP]


def _clump_the_review(script: Script) -> None:
    """STR-07: two consecutive review items from the same section."""
    prompts = [b for b in script.review if b.type is BeatType.PROMPT]
    assert len(prompts) >= 2
    first = script.card(prompts[0].card_id or "")
    second = script.card(prompts[1].card_id or "")
    assert first is not None and second is not None
    second.section_id = first.section_id


def _inflate_a_segment(script: Script) -> None:
    """SEG-01: a segment over the hard maximum."""
    script.sections[0].segments[0].beats[0].est_seconds = 500.0


def _overload_new_terms(script: Script) -> None:
    """SEG-03: more new terms in one segment than working memory will hold.

    Spread over two beats on purpose. One beat carrying five new terms is a property of the
    source and the rule reports it as a warning; five spread over a segment is the planner
    packing too much in, which it could have split.
    """
    segment = script.sections[0].segments[0]
    for i in range(2):
        segment.beats.append(
            Beat(
                id=beat_id(BeatType.EXPOSITION, "overloaded", str(i)),
                type=BeatType.EXPOSITION,
                text="Two more ideas arrive in this sentence.",
                concept_ids=[f"c_invented_{i}a", f"c_invented_{i}b"],
                spans=[Span(block_id="b_mutant")],
                est_seconds=2.0,
            )
        )


def _remove_an_answer(script: Script) -> None:
    """RET-01: a question the listener can never resolve."""
    for segment in script.segments():
        if any(b.type is BeatType.PROMPT for b in segment.beats):
            segment.beats = [b for b in segment.beats if b.type is not BeatType.ANSWER]
            return
    raise AssertionError("the fixture has no prompt to strand")


def _remove_a_pause(script: Script) -> None:
    """PAU-01: a prompt that is really a rhetorical question."""
    for beat in script.beats():
        if beat.type is BeatType.PROMPT:
            beat.pause_after = 0.0
            return
    raise AssertionError("the fixture has no prompt")


def _repeat_verbatim(script: Script) -> None:
    """REP-01: the same sentence twice, which feels like learning and is not."""
    exposition = next(
        b for b in script.beats() if b.type is BeatType.EXPOSITION and len(b.text.split()) > 12
    )
    segment = next(s for s in script.segments() if any(b.id == exposition.id for b in s.beats))
    segment.beats.append(
        Beat(
            id=beat_id(BeatType.CALLBACK, exposition.text, "mutant"),
            type=BeatType.CALLBACK,
            text=exposition.text,
            concept_ids=exposition.concept_ids,
            spans=exposition.spans,
            est_seconds=exposition.est_seconds,
        )
    )


def _crowd_a_callback(script: Script) -> None:
    """SPC-01: a scheduled exposure inside the minimum gap.

    Built rather than found. The violation needs a gap that is *past* the episode window and
    *inside* the minimum gap, in two different sections -- three conditions the fixture's own
    timeline satisfies only by accident, and would stop satisfying the moment the fixture grew a
    paragraph. So: introduce a concept at the end of one section, wait ninety seconds, and call
    it back at the start of the next.
    """
    first, second = script.sections[0], script.sections[1]
    concept_id = "c_crowded"
    first.segments[-1].beats.extend(
        [
            Beat(
                id=beat_id(BeatType.EXPOSITION, "crowded introduction", "mutant"),
                type=BeatType.EXPOSITION,
                text="Here is an idea that will come back too soon.",
                concept_ids=[concept_id],
                spans=[Span(block_id="b_mutant")],
                est_seconds=1.0,
            ),
            Beat(
                id=beat_id(BeatType.EXPOSITION, "ninety seconds of filler", "mutant"),
                type=BeatType.EXPOSITION,
                text="Ninety seconds pass.",
                spans=[Span(block_id="b_mutant")],
                est_seconds=90.0,
            ),
        ]
    )
    second.segments[0].beats.insert(
        0,
        Beat(
            id=beat_id(BeatType.CALLBACK, "crowded callback", "mutant"),
            type=BeatType.CALLBACK,
            text="Back to that for a moment. It matters here too.",
            concept_ids=[concept_id],
            spans=[Span(block_id="b_mutant")],
            est_seconds=1.0,
        ),
    )


def _ungrounded_exposition(script: Script) -> None:
    """GRD-01: a claim about the document with nothing behind it."""
    next(b for b in script.beats() if b.type is BeatType.EXPOSITION).spans = []


def _share_an_anchor(script: Script) -> None:
    """IMG-02: two ideas that retrieve each other."""
    concepts = list(script.registry.values())[:2]
    assert len(concepts) == 2
    for concept in concepts:
        concept.anchor = Anchor(text="a candle burning down inside a sealed jar")


def _analogy_without_a_limit(script: Script) -> None:
    """ANA-01: the model refuses to build one, so this one is assembled around it."""
    concept = next(iter(script.registry.values()))
    # Assignment goes through validation, which is the first line of defence and refuses this.
    # Writing straight into the field is the only way to build the artefact the linter exists
    # to catch -- and the linter has to catch it, because in M5 the analogy arrives as JSON
    # from a model rather than through this constructor.
    concept.__dict__["analogy"] = Analogy.model_construct(
        text="it is like a scab that keeps re-forming", limit=""
    )


def _unmarked_anchor(script: Script) -> None:
    """VOI-02: an anchor said without saying it is ours."""
    beat = _first(script, BeatType.ANCHOR)
    beat.text = "A cast-iron pan seasons itself the first time it is heated."


def _anchor_without_a_pause(script: Script) -> None:
    """PAU-02: an image the listener is given no time to form."""
    _first(script, BeatType.ANCHOR).pause_after = 0.0


def _invented_number(script: Script) -> None:
    """GRD-03: the worst failure this system can produce, in its cheapest form."""
    beat = _first(script, BeatType.GLOSS)
    beat.text = beat.text.rstrip(".") + ", and it costs 41.85 percent of capacity."


def _first(script: Script, kind: BeatType) -> Beat:
    beat = next((b for b in script.beats() if b.type is kind), None)
    assert beat is not None, f"the fixture has no {kind.value} beat"
    return beat


def _split_a_sentence(script: Script) -> None:
    """TTS-04: a chunk that ends mid-sentence."""
    beat = next(b for b in script.beats() if b.type is BeatType.EXPOSITION)
    beat.text = beat.text.rstrip(".?!") + " and then"


CASES: list[tuple[str, Mutator]] = [
    ("STR-02", _break_prequestions),
    ("STR-06", _remove_recaps),
    ("STR-07", _clump_the_review),
    ("SEG-01", _inflate_a_segment),
    ("SEG-03", _overload_new_terms),
    ("RET-01", _remove_an_answer),
    ("PAU-01", _remove_a_pause),
    ("REP-01", _repeat_verbatim),
    ("SPC-01", _crowd_a_callback),
    ("GRD-01", _ungrounded_exposition),
    ("IMG-02", _share_an_anchor),
    ("ANA-01", _analogy_without_a_limit),
    ("VOI-02", _unmarked_anchor),
    ("PAU-02", _anchor_without_a_pause),
    ("GRD-03", _invented_number),
    ("TTS-04", _split_a_sentence),
]
IDS = [case[0] for case in CASES]


@pytest.mark.parametrize(("rule_id", "mutate"), CASES, ids=IDS)
def test_the_clean_plan_passes(
    rule_id: str, mutate: Mutator, elaborated_script: Script, study_profile: Profile
) -> None:
    assert _errors(_rule(rule_id, study_profile), elaborated_script) == []


@pytest.mark.parametrize(("rule_id", "mutate"), CASES, ids=IDS)
def test_the_broken_plan_fails(
    rule_id: str, mutate: Mutator, elaborated_script: Script, study_profile: Profile
) -> None:
    broken = elaborated_script.model_copy(deep=True)
    mutate(broken)
    assert _errors(_rule(rule_id, study_profile), broken), f"{rule_id} did not notice"


def test_every_rule_has_a_fixture_pair(study_profile: Profile) -> None:
    """A rule with no failing example has never been shown to work."""
    assert {r.id for r in script_rules(study_profile)} == set(IDS)


def test_a_rule_only_reports_its_own_id(elaborated_script: Script, study_profile: Profile) -> None:
    for rule in script_rules(study_profile):
        assert all(v.rule == rule.id for v in rule.check(elaborated_script))
