"""One passing and one failing example for every cross-artefact lint rule.

Same discipline as :mod:`tests.unit.test_script_lint`, and for the same reason: a rule with no
failing example has never been shown to work. The difference is what gets mutated. These rules
are statements about the *relationship* between two artefacts, so half of the cases break the
document and half break the written track, and either one has to be enough on its own.

The failure that matters most is the quiet one. ``NUM-06`` and ``MTH-04`` both fail by a value
simply not being anywhere, which produces a shorter ``study.md`` and no other symptom at all --
no exception, no lint error from any other rule, and an audio track that is word-for-word what
it was. That is the shape of every regression this family exists to catch.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from mimem.clean.sentences import sentence_spans
from mimem.config import Listener, Profile
from mimem.ir import Block, BlockKind, BlockRole, Document, Script, TriageAction, TriageDecision
from mimem.lint.artefact_rules import ARTEFACT_RULE_TYPES, ArtefactRule, Bundle, artefact_rules
from mimem.plan import plan
from mimem.render import render

Mutator = Callable[[Bundle], Bundle]


@pytest.fixture
def bundle(interphase_doc: Document, study_profile: Profile) -> Bundle:
    """A clean build of the fixture paper, with an equation and a value to lose.

    The shared fixture writes its numbers out in words, which is realistic for a paper that has
    already been verbalized and useless here: ``NUM-06`` is a rule about digits surviving into
    the written track, and there have to be some. One sentence carries a real one.
    """
    doc = interphase_doc.model_copy(deep=True)
    results = next(
        b for b in doc.blocks if b.role is BlockRole.RESULTS and b.kind is BlockKind.PARAGRAPH
    )
    results.text += " Capacity fade averaged 0.0837 % per cycle over the run."
    results.sentences = sentence_spans(results.text)
    doc.blocks.append(
        Block(
            id="b_equation",
            kind=BlockKind.EQUATION,
            text="Q(n) = Q_0 - k * sqrt(n)",
            order=len(doc.blocks),
            triage=TriageDecision(action=TriageAction.DROP, rule="DUR-02", reason="no time for it"),
        )
    )
    from mimem.concepts import build as build_registry

    registry = build_registry(doc, Listener())
    script = plan(doc, registry, study_profile, Listener())
    artefacts = render(script, doc)
    return Bundle(script, doc, artefacts.audio, artefacts.study)


def _rule(rule_id: str, profile: Profile) -> ArtefactRule:
    return next(r for r in artefact_rules(profile) if r.id == rule_id)


def _fired(rule: ArtefactRule, bundle: Bundle) -> list[str]:
    return [v.message for v in rule.check(bundle) if v.severity is rule.severity]


# -- the mutations ----------------------------------------------------------------------------


def _narrate_the_acknowledgements(bundle: Bundle) -> Bundle:
    """COH-01: a block triage dropped as furniture, said aloud anyway.

    Written straight into the audio rather than into the plan, because that is how it would
    really happen: a beat builder that reads the wrong list, or an adapter that never labelled
    the block, and the script is internally consistent the whole time.
    """
    sentence = (
        "We thank the cleanroom staff for the release etch and two anonymous reviewers "
        "for their patience with an earlier draft."
    )
    bundle.doc.blocks.append(
        Block(
            id="b_ack",
            kind=BlockKind.PARAGRAPH,
            role=BlockRole.ACKNOWLEDGEMENT,
            text=sentence,
            order=len(bundle.doc.blocks),
            triage=TriageDecision(
                action=TriageAction.DROP, rule="COH-01", reason="acknowledgement carries no content"
            ),
        )
    )
    return Bundle(bundle.script, bundle.doc, bundle.audio + "\n\n" + sentence, bundle.study)


def _lose_the_equation(bundle: Bundle) -> Bundle:
    """MTH-04: the written track stops carrying an equation nobody narrated."""
    stripped = "\n".join(line for line in bundle.study.splitlines() if "Q(n)" not in line)
    return Bundle(bundle.script, bundle.doc, bundle.audio, stripped)


def _lose_a_value(bundle: Bundle) -> Bundle:
    """NUM-06: a value the audio spoke as words, gone from the only track that had it exactly."""
    from mimem.lint.artefact_rules import ExactValuesSurviveInWriting

    rule = ExactValuesSurviveInWriting()
    for beat in bundle.script.beats():
        for match in rule.VALUE.finditer(beat.written_text or ""):
            value = match.group(0).strip()
            if value in bundle.study:
                return Bundle(
                    bundle.script,
                    bundle.doc,
                    bundle.audio,
                    bundle.study.replace(value, "roughly that"),
                )
    raise AssertionError("the fixture has no value to lose")


CASES: list[tuple[str, Mutator]] = [
    ("COH-01", _narrate_the_acknowledgements),
    ("MTH-04", _lose_the_equation),
    ("NUM-06", _lose_a_value),
]
IDS = [case[0] for case in CASES]


@pytest.mark.parametrize(("rule_id", "mutate"), CASES, ids=IDS)
def test_the_clean_build_passes(
    rule_id: str, mutate: Mutator, bundle: Bundle, study_profile: Profile
) -> None:
    assert _fired(_rule(rule_id, study_profile), bundle) == []


@pytest.mark.parametrize(("rule_id", "mutate"), CASES, ids=IDS)
def test_the_broken_build_fails(
    rule_id: str, mutate: Mutator, bundle: Bundle, study_profile: Profile
) -> None:
    broken = mutate(bundle)
    assert _fired(_rule(rule_id, study_profile), broken), f"{rule_id} did not notice"


def test_every_rule_has_a_fixture_pair(study_profile: Profile) -> None:
    """A rule with no failing example has never been shown to work."""
    assert {r.id for r in artefact_rules(study_profile)} == set(IDS)
    assert len(ARTEFACT_RULE_TYPES) == len(CASES)


def test_a_dropped_equation_still_reaches_the_written_track(bundle: Bundle) -> None:
    """MTH-04 is a promise about the renderer, so the renderer has to keep it.

    The equation in the fixture is dropped by triage and never becomes a beat. Before the
    appendix existed it was simply gone -- and the rule would have been unfailable in the
    direction that matters, because nothing would have put it there in the first place.
    """
    assert "Q(n) = Q_0 - k * sqrt(n)" in bundle.study
    assert "Equations not in the programme" in bundle.study


def test_a_report_says_what_it_could_not_check(
    interphase_script: Script, study_profile: Profile
) -> None:
    """lint_script has no document, and must not report clean about rules it never ran."""
    from mimem.lint import lint_script

    partial = lint_script(interphase_script, profile=study_profile)
    assert {line.split(":")[0] for line in partial.skipped} == set(IDS)
    assert "not checked here" in partial.summary()


@pytest.mark.parametrize(
    ("sentence", "fires"),
    [
        ("We acknowledge that artificial intelligence can play additional roles.", False),
        ("The authors acknowledge that this is a limitation of the study.", False),
        ("We acknowledge support from the Research Council of Norway.", True),
        ("We gratefully acknowledge the financial support of the sponsor.", True),
        ("We acknowledge access to the beamline at the synchrotron.", True),
        ("We thank the cleanroom staff for the release etch.", True),
    ],
)
def test_acknowledge_needs_its_object(sentence: str, fires: bool) -> None:
    """ "We acknowledge" is two different sentences, and only one is an acknowledgement.

    "We acknowledge support from X" is a credit. "We acknowledge that X can also do Y, but we
    narrow our focus" is a concession, and ordinary scientific prose. The bare verb failed a
    real paper's build -- as an *error*, so it also refused to synthesise the audio -- over the
    second kind.
    """
    import re

    from mimem.lint.artefact_rules import DropListRespected

    matched = any(
        re.search(pattern, sentence, re.IGNORECASE) for pattern, _ in DropListRespected.FURNITURE
    )
    assert matched is fires
