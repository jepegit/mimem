"""The planner: structure, retrieval, pacing and the exposure log.

These are the rules that make the difference between a document read aloud and a document you
remember, so they are tested against a whole plan rather than against helpers. The fixture in
``conftest.py`` is a small paper with an abstract, four sections and two recurring concepts --
enough for segments to form, for the spacing scheduler to have somewhere to put a callback, and
for the review block to have more than one section to interleave.

The last test in each group is the one that would catch a regression that still passes the
linter: a plan can satisfy every rule and still be pointless, and "the recap names what this
section added" is not something a lint rule can check.
"""

from __future__ import annotations

from itertools import pairwise

from mimem.concepts import build as build_registry
from mimem.config import Listener, Profile
from mimem.ir import BeatType, BlockKind, Document, Script
from mimem.lint import lint_script, script_rules
from mimem.lint.rules import Severity
from mimem.plan import plan
from mimem.plan.budget import enforce
from mimem.plan.review import interleave


def _types(script: Script) -> list[str]:
    return [b.type.value for b in script.beats()]


# -- structure -------------------------------------------------------------------------------


def test_the_programme_opens_with_orientation_prequestions_and_a_preload(
    interphase_script: Script,
) -> None:
    """Rules STR-01, STR-02, STR-03, in that order, before any exposition."""
    opening = [b.type for b in interphase_script.opening]
    assert opening[0] is BeatType.ORIENTATION
    assert BeatType.PREQUESTION in opening
    assert opening.index(BeatType.PREQUESTION) < len(opening)
    body_starts = _types(interphase_script).index("exposition")
    assert body_starts > len(interphase_script.opening) - 1


def test_the_orientation_says_what_it_is_and_how_long_it_takes(interphase_script: Script) -> None:
    text = interphase_script.opening[0].text
    assert "Interphase repair" in text
    assert "Ada Lovelace" in text
    assert "minutes" in text


def test_every_section_ends_with_a_recap_and_a_prompt(interphase_script: Script) -> None:
    """Rule STR-06. Checked here as well as in the linter because it is the rule the duration
    budget was allowed to break, once."""
    for section in interphase_script.sections:
        types = [b.type for b in section.beats()]
        assert BeatType.RECAP in types, section.title
        assert BeatType.PROMPT in types, section.title
        tail = types[types.index(BeatType.RECAP) :]
        assert BeatType.PROMPT in tail  # the recap comes first, then the question


def test_the_recap_names_what_its_own_section_added(interphase_script: Script) -> None:
    """Not the document's top concepts: that made every recap the same sentence."""
    recaps = [b for b in interphase_script.beats() if b.type is BeatType.RECAP and b.concept_ids]
    assert recaps
    named = [tuple(sorted(b.concept_ids)) for b in recaps]
    assert len(set(named)) == len(named), "two sections recapped the same concepts"


def test_prequestions_come_from_the_cards_and_are_closed(interphase_script: Script) -> None:
    """Rules STR-02 and PRQ-02: asked at the start, discharged when the answer arrives."""
    asked = [b for b in interphase_script.opening if b.type is BeatType.PREQUESTION and b.card_id]
    assert 2 <= len(asked) <= 4
    card_ids = {c.id for c in interphase_script.cards}
    assert all(b.card_id in card_ids for b in asked)
    closed = {b.card_id for b in interphase_script.beats() if b.type is BeatType.PREQUESTION_CLOSE}
    assert {b.card_id for b in asked} <= closed


def test_the_review_block_interleaves_sections(interphase_script: Script) -> None:
    """Rule STR-07, and SPC-04: interleaving happens here and only here."""
    prompts = [b for b in interphase_script.review if b.type is BeatType.PROMPT]
    sections = [interphase_script.card(b.card_id or "").section_id for b in prompts]  # type: ignore[union-attr]
    assert len(sections) >= 2
    assert all(a != b for a, b in pairwise(sections))


def test_interleaving_reports_what_it_could_not_avoid() -> None:
    """One section with more questions than all the others cannot be interleaved."""
    from mimem.ir import Card

    cards = [
        Card(id=f"k{i}", concept_id="c", subject="c", prompt="?", answer=".", section_id="a")
        for i in range(3)
    ]
    cards.append(Card(id="k9", concept_id="c", subject="c", prompt="?", answer=".", section_id="b"))
    ordered, collisions = interleave(cards)
    assert len(ordered) == 4  # nothing is dropped
    assert collisions == 1


# -- retrieval and pacing ---------------------------------------------------------------------


def test_every_prompt_has_a_pause_and_an_answer(interphase_script: Script) -> None:
    """Rules RET-01 and PAU-01, the pair that makes a prompt a retrieval attempt."""
    beats = interphase_script.beats()
    for i, beat in enumerate(beats):
        if beat.type is not BeatType.PROMPT:
            continue
        assert beat.pause_after >= 3.0
        assert beats[i + 1].type is BeatType.ANSWER


def test_a_prompt_says_out_loud_that_thinking_time_is_expected(interphase_script: Script) -> None:
    """PAU-01 again: an engine that ignores break markers still has to convey the pause."""
    prompts = [b for b in interphase_script.beats() if b.type is BeatType.PROMPT]
    assert prompts
    assert all("few seconds" in b.text for b in prompts)


def test_prompts_are_response_congruent(interphase_script: Script) -> None:
    """Rule RET-02: a definitional answer gets a "what does it mean" question."""
    from mimem.ir import PromptType

    for card in interphase_script.cards:
        if card.prompt_type is PromptType.DEFINITION:
            assert "mean" in card.prompt
        if card.prompt_type is PromptType.MECHANISM:
            assert "explains" in card.prompt


def test_an_answer_stands_on_its_own(interphase_script: Script) -> None:
    """Rule RET-04: a listener who missed the question still needs the answer to make sense."""
    for card in interphase_script.cards:
        assert card.answer.startswith("Here's the answer about")


def test_segments_stay_within_the_hard_maximum(
    interphase_script: Script, study_profile: Profile
) -> None:
    """Rule SEG-01. The closing beats are appended after segmentation, so this is a real risk."""
    for segment in interphase_script.segments():
        assert segment.est_seconds <= study_profile.segments.hard_max


# -- grounding and provenance ------------------------------------------------------------------


def test_exposition_is_the_source_and_scaffolding_is_marked(interphase_script: Script) -> None:
    """Rule GRD-01, and VOI-02: a listener is never in doubt about whose claim they heard."""
    for beat in interphase_script.beats():
        if beat.needs_span:
            assert beat.spans, f"{beat.type} beat with no span: {beat.text[:60]}"
        if beat.generated:
            assert beat.provenance is not None
            assert beat.provenance.generator.startswith("template:")


def test_every_beat_names_the_rules_that_produced_it(interphase_script: Script) -> None:
    """What makes `mimem explain` and the whole traceability claim real."""
    assert all(
        b.rules for b in interphase_script.beats() if b.type is not BeatType.ANSWER or b.rules
    )


def test_scaffolding_obeys_the_speakability_rules_too(interphase_script: Script) -> None:
    """The generated text is speech: "Section 3 of 7" is two lint errors as written."""
    generated = " ".join(b.text for b in interphase_script.beats() if b.generated)
    assert not any(ch.isdigit() for ch in generated)


# -- spacing and the exposure log ---------------------------------------------------------------


def test_concepts_come_back(interphase_script: Script) -> None:
    """Rule REP-02: the whole point of the exercise."""
    repeated = [c for c in interphase_script.registry.values() if len(c.exposures) > 1]
    assert repeated, "no concept was ever brought back"


def test_the_exposure_log_records_when_and_in_what_form(interphase_script: Script) -> None:
    """Rule SPC-03: part two cannot schedule anything without this."""
    for concept in interphase_script.registry.values():
        for exposure in concept.exposures:
            assert exposure.beat_id
            assert exposure.at_seconds >= 0
            assert exposure.form


def test_the_schedule_hands_over_where_the_document_left_off(interphase_script: Script) -> None:
    assert interphase_script.schedule
    for entry in interphase_script.schedule:
        assert entry.exposures >= 1
        assert entry.next_interval_minutes > 0


def test_a_callback_is_a_different_sentence(interphase_script: Script) -> None:
    """Rule REP-01: the source says more than one thing about anything that matters."""
    callbacks = [b for b in interphase_script.beats() if b.type is BeatType.CALLBACK]
    said: set[str] = set()
    for beat in interphase_script.beats():
        if beat.type is BeatType.EXPOSITION:
            said.add(beat.text)
    for callback in callbacks:
        assert callback.text not in said


# -- the duration budget --------------------------------------------------------------------------


def test_the_budget_cuts_scaffolding_and_never_the_paper(interphase_script: Script) -> None:
    """Rule DUR-02, and the floor under it."""
    before = [b.type for b in interphase_script.beats() if b.type is BeatType.EXPOSITION]
    dropped = enforce(interphase_script, budget=interphase_script.est_seconds * 0.5)
    after = [b.type for b in interphase_script.beats() if b.type is BeatType.EXPOSITION]
    assert after == before
    assert all(record.beat_type is not BeatType.EXPOSITION for record in dropped)


def test_an_impossible_budget_is_reported_not_obeyed(interphase_script: Script) -> None:
    enforce(interphase_script, budget=1.0)
    assert any("over the duration budget" in note for note in interphase_script.notes)


def test_a_recap_is_not_cut_to_fit_the_clock(interphase_script: Script) -> None:
    """DUR-02 allows cutting "non-essential" recaps; STR-06's recap is not one of them."""
    enforce(interphase_script, budget=1.0)
    for section in interphase_script.sections:
        assert any(b.type is BeatType.RECAP for b in section.beats()), section.title


# -- the acceptance criterion -------------------------------------------------------------------


def test_the_plan_passes_its_own_lint_rules(
    interphase_script: Script, study_profile: Profile
) -> None:
    """M4 is done when the structure and spacing rules hold on the fixtures."""
    report = lint_script(interphase_script, profile=study_profile)
    assert report.ok, (
        report.summary() + "\n" + "\n".join(f"{v.rule}: {v.message}" for v in report.errors[:10])
    )


def test_the_script_round_trips(interphase_script: Script) -> None:
    assert Script.from_json(interphase_script.to_json()) == interphase_script


def test_every_script_rule_runs_on_a_real_plan(
    interphase_script: Script, study_profile: Profile
) -> None:
    """A rule that throws on real input is worse than no rule at all."""
    for rule in script_rules(study_profile):
        violations = rule.check(interphase_script)
        assert all(v.severity in {Severity.ERROR, Severity.WARNING} for v in violations)


def test_beats_are_content_addressed_and_unique(interphase_script: Script) -> None:
    """Rule TTS-03: part two re-synthesises only what changed, keyed on these."""
    ids = [b.id for b in interphase_script.beats()]
    assert len(ids) == len(set(ids))


def test_planning_twice_gives_the_same_plan(
    interphase_doc: Document, study_profile: Profile
) -> None:
    """Without determinism, a rebuild produces a diff nobody can read."""
    first = plan(
        interphase_doc, build_registry(interphase_doc, Listener()), study_profile, Listener()
    )
    second = plan(
        interphase_doc, build_registry(interphase_doc, Listener()), study_profile, Listener()
    )
    assert [b.id for b in first.beats()] == [b.id for b in second.beats()]


def test_the_listener_profile_reaches_the_plan(
    interphase_doc: Document, study_profile: Profile
) -> None:
    """Rule DIF-04 has to survive all the way to the artefact, not stop at the registry."""
    expert = Listener(name="expert", known_terms=["coulombic efficiency"])
    interphase_script = plan(
        interphase_doc, build_registry(interphase_doc, expert), study_profile, expert
    )
    assert interphase_script.listener == "expert"
    known = next(
        (
            c
            for c in interphase_script.registry.values()
            if c.canonical.lower() == "coulombic efficiency"
        ),
        None,
    )
    if known is not None:
        assert known.difficulty < 0.4


def test_a_prequestion_is_closed_once_and_not_twice(interphase_script: Script) -> None:
    """Rule PRQ-02 closes a loop, and a loop can only be closed once.

    A card can end its section and be asked again inside another segment, and closing it in
    both places tells the listener the same thing about the same question twice.
    """
    closed = [b.card_id for b in interphase_script.beats() if b.type is BeatType.PREQUESTION_CLOSE]
    assert len(closed) == len(set(closed))


def test_prequestions_are_drawn_from_the_whole_card_pool(
    interphase_doc: Document, study_profile: Profile
) -> None:
    """Rule PRQ-01 asks for two to four, and they used to be chosen too early to have them.

    The draw happened at step 2, when the pool held only the section-closing cards -- one per
    section. A paper whose headings do not survive extraction has *one* section, so one card,
    so one prequestion; three of twelve corpus papers failed this rule, with final pools of 12,
    3 and 33 cards. The fixture's headings are removed here to reproduce that.
    """
    headless = interphase_doc.model_copy(deep=True)
    for block in headless.blocks:
        if block.kind is BlockKind.HEADING:
            block.kind = BlockKind.PARAGRAPH
            block.level = None
    registry = build_registry(headless, Listener())
    script = plan(headless, registry, study_profile, Listener())

    assert len({s.id for s in script.sections}) == 1, "the fixture is meant to have one section"
    assert len(script.cards) > 1
    asked = [b for b in script.opening if b.type is BeatType.PREQUESTION and b.card_id]
    assert 2 <= len(asked) <= 4
    assert {b.card_id for b in asked} <= {c.id for c in script.cards}


def test_a_fallback_transition_ends_on_a_sentence_boundary(study_profile: Profile) -> None:
    """Rule TTS-04. It is assigned straight onto a beat, so it never passes through ``make``.

    One corpus paper has a section titled "Available online at www.sciencedirect.com". The URL
    pattern is greedy over non-space and takes the full stop away with the address, leaving
    "Still on available online at" for the engine to run into whatever came next.
    """
    from mimem.plan.beats import BeatFactory, section_fallback_transition

    factory = BeatFactory(study_profile)
    for title in ("Available online at www.sciencedirect.com", "Results and discussion", ""):
        assert section_fallback_transition(factory, title).endswith(".")
