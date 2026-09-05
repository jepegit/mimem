"""Rule GRD-03: the check that makes trusting a model possible.

The design rules call a flipped sign or a mangled number "the worst failure this system can
produce", and they are right: a clumsy sentence is audible, and a wrong number is not. So the
tests here are mostly adversarial — plausible sentences with one thing wrong in them, which is
the only interesting case. A sentence that is obviously wrong was never the risk.
"""

from __future__ import annotations

import pytest

from mimem.verify import Severity, check, numbers_in, verdict

SOURCE = (
    "The resulting capacity loss was measured at 0.0837 % per cycle over 500 cycles, "
    "i.e. a retention of 82.1 ± 1.4 % at end of test (p < 0.001). Volume changes during "
    "lithiation can exceed 300 % for silicon-based anodes, and the interphase thickness "
    "increased from 20 nm to 140 nm. First described by Peled in 1979."
)


def _kinds(findings) -> list[str]:
    return [f.kind for f in findings]


# -- numbers ---------------------------------------------------------------------------------


def test_a_faithful_sentence_passes() -> None:
    generated = "The cell retains 82.1 % of its capacity after 500 cycles."
    assert check(generated, SOURCE) == []


def test_a_mangled_number_is_caught() -> None:
    """A transposed digit reads perfectly and is wrong."""
    findings = check("The cell retains 82.7 % after 500 cycles.", SOURCE)
    assert "number" in _kinds(findings)
    assert not verdict(findings)


def test_an_invented_number_is_caught() -> None:
    """The arithmetic nobody asked for: 0.0837 x 500 is not in the paper."""
    findings = check("That adds up to 41.85 % over the run.", SOURCE)
    assert [f.value for f in findings if f.kind == "number"] == ["41.85"]


def test_formatting_differences_are_not_errors() -> None:
    """0,0837 and 0·0837 and 0.0837 are one number; so are 82.10 and 82.1."""
    assert check("Loss of 0,0837 % per cycle.", SOURCE) == []
    assert check("Loss of 0·0837 % per cycle.", SOURCE) == []
    assert check("Retention of 82.10 %.", SOURCE) == []


def test_thousands_separators_survive_the_round_trip() -> None:
    assert numbers_in("1,500 cells") == numbers_in("1500 cells")
    assert numbers_in("0.0837") == ["0.0837"]


def test_a_year_the_source_does_not_state() -> None:
    findings = check("First described by Peled in 1997.", SOURCE)
    assert "year" in _kinds(findings)


# -- names -----------------------------------------------------------------------------------


def test_an_invented_name_is_a_warning_not_an_error() -> None:
    """The false-positive rate on ordinary English is not zero, so this informs rather than
    fails: an error nobody can act on is noise."""
    findings = check("First described by Nakamura in 1979.", SOURCE)
    names = [f for f in findings if f.kind == "name"]
    assert names and names[0].severity is Severity.WARNING
    assert verdict(findings)  # a warning does not fail the gate


def test_a_sentence_opening_is_not_a_name() -> None:
    assert not [f for f in check("Silicon swells on lithiation.", SOURCE) if f.kind == "name"]


def test_an_acronym_is_not_a_name() -> None:
    """SYM-02 owns acronyms; flagging SEI here would fire on every paper."""
    assert not [f for f in check("The SEI forms at 20 nm.", SOURCE) if f.kind == "name"]


# -- directions ------------------------------------------------------------------------------


def test_a_flipped_direction_is_caught() -> None:
    """The failure that reads perfectly: the source says increased, the sentence says decreased."""
    findings = check("The interphase thickness decreased over the run.", SOURCE)
    assert "direction" in _kinds(findings)
    assert not verdict(findings)


def test_the_right_direction_passes() -> None:
    assert check("The interphase thickness increased over the run.", SOURCE) == []


def test_a_direction_the_source_never_discusses_is_not_flagged() -> None:
    """Only the *opposite* being present makes it a flip. Absence is not evidence."""
    assert not [
        f for f in check("The cell runs slower in the cold.", SOURCE) if f.kind == "direction"
    ]


# -- the gate --------------------------------------------------------------------------------


def test_the_gate_is_only_as_wide_as_the_cited_spans() -> None:
    """Checking against the whole document would pass a sentence that mixes up two results."""
    span = "Volume changes during lithiation can exceed 300 % for silicon-based anodes."
    findings = check("The capacity loss was 0.0837 % per cycle.", span)
    assert not verdict(findings)


@pytest.mark.parametrize(
    "generated",
    [
        "It swells by more than 300 %.",
        "Retention was 82.1 ± 1.4 % at end of test.",
        "The layer grew from 20 nm to 140 nm.",
    ],
)
def test_faithful_paraphrases_pass(generated: str) -> None:
    assert verdict(check(generated, SOURCE))
