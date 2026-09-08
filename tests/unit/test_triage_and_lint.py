"""Triage, narration and the lint suite.

Triage is the stage with the most leverage (deleting beats explaining) and therefore the most
risk, so these tests care as much about what is *kept* as about what is dropped.
"""

from __future__ import annotations

import pytest

from mimem.config import Profile
from mimem.ir import Block, BlockKind, BlockRole, Document, SourceMeta, TriageAction, block_id
from mimem.lint import Severity, lint
from mimem.render import narrate
from mimem.triage import drop_report, dropped, retained, triage


def _doc(*items: tuple[str, str, str]) -> Document:
    """(kind, role, text) triples."""
    blocks = [
        Block(
            id=block_id(kind, 1, i, text),
            kind=BlockKind(kind),
            role=BlockRole(role),
            text=text,
            order=i,
            page=1,
        )
        for i, (kind, role, text) in enumerate(items)
    ]
    return Document(id="d", source=SourceMeta(format="pdf", title="A Paper"), blocks=blocks)


@pytest.fixture
def profile() -> Profile:
    return Profile(name="test")


# -- triage ----------------------------------------------------------------------------------


def test_page_furniture_and_back_matter_are_dropped() -> None:
    doc = triage(
        _doc(
            ("page_artifact", "unknown", "J. Power Sources 512"),
            ("reference", "references", "[1] E. Peled, 1979."),
            ("paragraph", "acknowledgement", "We thank the beamline staff."),
            ("paragraph", "funding", "Supported by grant 000000."),
            ("paragraph", "results", "Capacity fell steadily over 500 cycles."),
        )
    )
    kept = retained(doc)
    assert len(kept) == 1
    assert kept[0].text.startswith("Capacity fell")
    assert len(dropped(doc)) == 4


def test_every_decision_carries_a_reason_and_a_rule() -> None:
    """Rule COH-05: nothing disappears without a trace."""
    doc = triage(_doc(("paragraph", "results", "A real sentence about results.")))
    decision = doc.blocks[0].triage
    assert decision is not None
    assert decision.rule.startswith("COH-")
    assert decision.reason


@pytest.mark.parametrize(
    "text",
    [
        "The remainder of this paper is organized as follows.",
        "The authors declare no conflicts of interest.",
        "This is an open access article distributed under a CC-BY licence.",
        "RESEARCH",
        "Ionics (2026) 32:7477-7499 https://doi.org/10.1007/s11581-026-07224-5",
    ],
)
def test_boilerplate_patterns(text: str) -> None:
    doc = triage(_doc(("paragraph", "body", text)))
    assert doc.blocks[0].triage.action is TriageAction.DROP


def test_boilerplate_beats_transform() -> None:
    """A journal citation line is symbol-dense enough to look like an equation. Announcing
    "there is an equation here" about it is worse than saying nothing."""
    doc = triage(_doc(("equation", "body", "Ionics (2026) 32:7477 https://doi.org/10.1007/x")))
    assert doc.blocks[0].triage.action is TriageAction.DROP


def test_figures_tables_and_equations_are_transformed_not_dropped() -> None:
    doc = triage(
        _doc(
            ("table", "results", "Cell | Capacity"),
            ("equation", "results", "C(t) = C0 exp(-t/tau)"),
        )
    )
    assert all(b.triage.action is TriageAction.TRANSFORM for b in doc.blocks)
    assert len(retained(doc)) == 2  # retained, awaiting the M5 verbalizers


def test_prose_built_on_missing_mathematics_is_not_read() -> None:
    text = " ".join(["inline-eq Vector of features"] * 4)
    doc = triage(_doc(("paragraph", "methods", text)))
    assert doc.blocks[0].triage.action is TriageAction.TRANSFORM


def test_triage_is_idempotent() -> None:
    doc = triage(_doc(("paragraph", "results", "A sentence that carries the argument.")))
    before = [b.triage for b in doc.blocks]
    assert [b.triage for b in triage(doc).blocks] == before


def test_drop_report_names_the_rule_and_the_reason() -> None:
    doc = triage(
        _doc(
            ("paragraph", "acknowledgement", "We thank everyone involved in the work."),
            ("paragraph", "results", "Capacity fell steadily over five hundred cycles."),
        )
    )
    report = drop_report(doc)
    assert "COH-01" in report
    assert "acknowledgement" in report
    assert "retained" in report


# -- narration -------------------------------------------------------------------------------


def test_narration_speaks_the_title_and_the_content(profile: Profile) -> None:
    doc = triage(
        _doc(
            ("heading", "results", "3. Results"),
            ("paragraph", "results", "Capacity fell by 0.5 % per cycle."),
        )
    )
    out = narrate(doc, profile)
    assert out.audio.startswith("A Paper.")
    assert "Section: 3. Results" not in out.audio  # the heading is verbalized too
    assert "zero point five percent" in out.audio
    assert out.spoken_words > 0


def test_headings_are_verbalized(profile: Profile) -> None:
    """Easy to forget, because a heading looks like a label rather than a sentence."""
    doc = triage(_doc(("heading", "results", "The Tesla 4680 cell")))
    assert "4680" not in narrate(doc, profile).audio


def test_the_written_track_keeps_what_the_audio_track_could_not(profile: Profile) -> None:
    """Rule NUM-06: reduction is audio-only; the exact value always survives."""
    doc = triage(_doc(("paragraph", "results", "Retention was 82.137 % at cycle 500.")))
    out = narrate(doc, profile)
    assert "82.137" in out.study
    assert "82.137" not in out.audio


def test_pending_kinds_are_announced_not_dropped(profile: Profile) -> None:
    doc = triage(_doc(("table", "results", "Cell | Capacity")))
    out = narrate(doc, profile)
    assert "written notes" in out.audio
    assert out.pending == {"table": 1}


# -- lint ------------------------------------------------------------------------------------


def test_clean_narration_passes() -> None:
    report = lint("Capacity fell by zero point five percent per cycle. The trend was steady.")
    assert report.ok
    assert not report.violations


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("The value was 82 percent.", "NUM-02"),
        ("As shown in earlier work [12].", "SENT-03"),
        ("Smith et al. reported this.", "CIT-01"),
        ("See https://example.com for more.", "CIT-01"),
        ("The result, e.g. this one, held.", "SENT-04"),
        ("A value of 5 § was found.", "TTS-01"),
    ],
)
def test_each_defect_is_caught_by_its_rule(text: str, rule: str) -> None:
    assert rule in {v.rule for v in lint(text).violations}


def test_a_defect_is_reported_once_by_the_rule_that_owns_it() -> None:
    """Digits belong to NUM-02 and brackets to SENT-03; TTS-01 must not double-report them."""
    rules = [v.rule for v in lint("value 42").violations]
    assert rules.count("TTS-01") == 0
    assert "NUM-02" in rules


def test_long_sentences_warn_rather_than_fail() -> None:
    long_sentence = "This sentence " + "goes on and on " * 12 + "without stopping."
    report = lint(long_sentence)
    assert report.ok  # warnings do not fail the build
    assert any(v.rule == "SENT-01" and v.severity is Severity.WARNING for v in report.violations)


def test_report_summarises_by_rule() -> None:
    report = lint("Values 1, 2 and 3 with [4].")
    assert "NUM-02" in report.summary()
    assert not report.ok


def test_a_row_of_panel_labels_is_dropped() -> None:
    """Lifted out of a figure, it is a legend for regions of a picture and carries no sentence.
    Narrated, it became "a, b, c, d, e, f." spoken aloud."""
    from mimem.ir import Block, BlockKind
    from mimem.triage.rules import _decide

    decision = _decide(Block(id="b", kind=BlockKind.PARAGRAPH, text="(a) (b) (c) (d) (e) (f)"))
    assert decision.action is TriageAction.DROP
    assert decision.reason == "panel labels"


# -- back matter the anchored patterns could not reach ------------------------------------------


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        # A whole back-matter section in one paragraph, heading and all. Every boilerplate
        # pattern is anchored at the start of the block, and the declaration is in the middle
        # of it -- so dropping on the heading is what makes the block reachable at all.
        (
            "■AUTHOR INFORMATION Notes The authors declare no competing financial "
            "interest. ■ACKNOWLEDGMENTS We gratefully acknowledge funding from the "
            "Department of Energy Office of Basic Energy Sciences.",
            "back matter",
        ),
        (
            "■AUTHOR INFORMATION Corresponding Authors *E-mail: stevenson@example.edu. "
            "Present Address: Chemical and Biomolecular Engineering.",
            "back matter",
        ),
        # One character of furniture in front of the label was enough to miss the block. The
        # postcode and the telephone number in this one were the paper's only two lint errors.
        (
            "*Correspondence to: Wen-zhi Yang, PhD Ningbo Branch of China Academy of Ordnance "
            "Science, Ningbo 315103, P. R. China Tel/Fax: +86 574 87902102",
            "correspondence",
        ),
    ],
)
def test_a_marker_in_front_of_the_label_no_longer_hides_the_block(text: str, reason: str) -> None:
    doc = triage(_doc(("paragraph", "body", text)))
    decision = doc.blocks[0].triage
    assert decision is not None
    assert decision.action is TriageAction.DROP
    assert decision.rule == "COH-01"
    assert decision.reason == reason


def test_prose_that_opens_with_a_dash_is_still_prose() -> None:
    """The marker class includes the dash, which is the character that could run away with it."""
    text = (
        "- the interphase keeps consuming lithium at every cycle, which is why the coulombic "
        "efficiency never quite reaches one and the cell fades."
    )
    doc = triage(_doc(("paragraph", "body", text)))
    assert doc.blocks[0].triage.action is not TriageAction.DROP
