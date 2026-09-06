"""Defects found by running mimem on a ninety-eight page review, one test each.

The paper was a real one, handed over with "try to process this one", and it broke six things
that two synthetic fixtures and four other real papers had not. That is the argument for this
file existing separately: these are not tests of a design, they are tests of specific ways the
world turned out to be shaped, and each one is cheap insurance against a plausible-looking
refactor putting it back.

The pattern in every case is the same, and worth naming. None of these was a wrong *decision*.
Each was a pattern that matched slightly less than the thing it was written for -- a citation
stripper that understood "Section 2" but not "Section 2.1.4", a unit table that knew "H" was
the henry and did not know that "H2" is hydrogen, an acronym check that was right about the
first occurrence and wrong about the next two hundred and fifteen.
"""

from __future__ import annotations

import pytest

from mimem.config import Profile
from mimem.lint import lint
from mimem.verbalize import verbalize_text
from mimem.verbalize.numbers import verbalize_numbers


@pytest.fixture
def profile() -> Profile:
    return Profile(name="study")


# -- the verbalizer ---------------------------------------------------------------------------


def test_a_multi_level_section_reference_is_removed_whole(profile: Profile) -> None:
    """ "corresponding to Section 2.1.4" left ".1.4" behind, and said it out loud."""
    spoken = verbalize_text(
        "Gas signals are the earliest precursor, corresponding to Section 2.1.4, and matter most.",
        profile,
    )
    assert "1.4" not in spoken
    assert "2" not in spoken


def test_removing_a_reference_takes_its_preposition_with_it(profile: Profile) -> None:
    """Otherwise the sentence says "corresponding to, where..." in a confident voice."""
    spoken = verbalize_text("Gas is the precursor, corresponding to Section 2.1.4, here.", profile)
    assert "to," not in spoken


def test_a_reference_to_an_unnumbered_figure_is_removed(profile: Profile) -> None:
    """ "as shown in the figure" is as unfollowable as "as shown in Figure 4", and had no number
    for the pattern to anchor on."""
    spoken = verbalize_text(
        "Under four conditions, as shown in the figure, CO and CO2 dominate.", profile
    )
    assert "figure" not in spoken.lower()
    assert "CO two" in spoken


def test_a_sentence_opening_with_a_reference_does_not_start_on_a_comma(
    profile: Profile,
) -> None:
    spoken = verbalize_text("As presented in the table below, capacity falls.", profile)
    assert not spoken.startswith(",")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Section 2.3.1. Model Architectures", "two point three point one"),
        ("version 1.2.3 shipped", "one point two point three"),
        # One dot is an ordinary decimal and must not be caught by the multi-level pass.
        ("a value of 2.5 volts", "two point five volts"),
    ],
)
def test_a_dotted_number_is_spoken_to_its_last_level(text: str, expected: str) -> None:
    assert expected in verbalize_numbers(text)


def test_a_subscript_digit_becomes_a_spoken_number(profile: Profile) -> None:
    """The regression this caught was mine, one build after I introduced it.

    Normalizing look-alike characters is right, but doing it *after* the number verbalizer left
    "CO₂" as "CO2" with nothing left to say it -- a raw digit in the audio track, which is the
    single thing NUM-02 exists to prevent.
    """
    spoken = verbalize_text("Gas products include CO₂ and H₂ above 250 °C.", profile)
    assert "CO two" in spoken
    assert "H two" in spoken
    assert not any(c.isdigit() for c in spoken)


def test_the_increment_sign_is_not_the_only_delta(profile: Profile) -> None:
    """U+2206 and U+0394 are indistinguishable on the page and only one was in the table."""
    for delta in ("∆", "Δ"):
        assert "delta Q" in verbalize_text(f"features based on {delta}Q enable prediction", profile)


def test_hydrogen_is_not_square_henries() -> None:
    """ "H" is the henry, so "H2" read as an area. In a paper about venting hydrogen."""
    assert verbalize_numbers("the H2 concentration rose") == "the H two concentration rose"


def test_units_that_have_an_area_still_get_one() -> None:
    """The fix must not take squared metres with it."""
    assert "square centimetres" in verbalize_numbers("5 cm2 of electrode")
    assert "cubic metres" in verbalize_numbers("a 3 m3 tank")


# -- the linter -------------------------------------------------------------------------------


def test_an_expanded_acronym_is_not_reported() -> None:
    """SENT-04 reported all 670 uses of 80 acronyms, nearly all of them correctly expanded.

    A report that is four-fifths one rule being wrong does not get read, so the rule was worse
    than no rule at all.
    """
    text = "Thermal runaway, or TR, is the risk. TR begins at the anode. TR then spreads."
    assert not [v for v in lint(text).violations if v.rule == "SYM-02"]


def test_an_acronym_nobody_expands_is_reported_once() -> None:
    text = "The SOH fell steadily. SOH is what we track. A low SOH ends the test."
    violations = [v for v in lint(text).violations if v.rule == "SYM-02"]
    assert len(violations) == 1
    assert "SOH" in violations[0].message


def test_acronyms_do_not_fail_a_build() -> None:
    """When the source never expands its own acronym there is nothing to expand it to, and
    inventing one would be a worse failure than saying the letters."""
    assert lint("The SOH fell steadily.").ok


# -- the console ------------------------------------------------------------------------------


def test_the_report_survives_a_console_that_cannot_show_the_character() -> None:
    """A single U+2206 ended `mimem build` in a traceback on a stock Windows terminal.

    The artefacts had already been written; only the report died -- and it died while printing
    the lint violation that was trying to say what was wrong with the document.
    """
    import io

    from mimem.cli import _speakable_console

    console = _speakable_console()
    buffer = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="replace")
    console.file = buffer
    console.print("voltage curve evolution, ∆Q, enables prediction")  # must not raise
