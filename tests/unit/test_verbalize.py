"""Deterministic verbalization: numbers, units, citations, parentheses, symbols.

This is where the numbers live, so it is where the tests are densest. Rule NUM-01 makes exact
fidelity the default, which means a rounding bug here is not a cosmetic problem -- it is the
system confidently saying something the paper did not.
"""

from __future__ import annotations

import pytest

from mimem.config import CitationVerbosity, Listener, NumericFidelity, Profile
from mimem.verbalize import verbalize_text
from mimem.verbalize.citations import (
    count_superscript_citations,
    strip_superscript_citations,
    verbalize_citations,
)
from mimem.verbalize.numbers import (
    int_to_words,
    number_to_words,
    ordinal_to_words,
    verbalize_numbers,
)
from mimem.verbalize.parens import verbalize_parentheticals
from mimem.verbalize.symbols import verbalize_symbols
from mimem.verbalize.units import spoken_unit


@pytest.fixture
def profile() -> Profile:
    return Profile(name="test")


# -- numbers ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("n", "words"),
    [
        (0, "zero"),
        (7, "seven"),
        (13, "thirteen"),
        (21, "twenty one"),
        (100, "one hundred"),
        (123, "one hundred and twenty three"),
        (1000, "one thousand"),
        (2026, "two thousand and twenty six"),
        (7477, "seven thousand four hundred and seventy seven"),
        (1234567, "one million two hundred and thirty four thousand five hundred and sixty seven"),
        (-42, "minus forty two"),
    ],
)
def test_integers(n: int, words: str) -> None:
    assert int_to_words(n) == words


@pytest.mark.parametrize(
    ("n", "words"),
    [(1, "first"), (3, "third"), (12, "twelfth"), (13, "thirteenth"), (20, "twentieth"),
     (21, "twenty first"), (100, "one hundredth")],
)  # fmt: skip
def test_ordinals(n: int, words: str) -> None:
    assert ordinal_to_words(n) == words


def test_exact_fidelity_keeps_every_digit() -> None:
    """Rule NUM-01: the listener is a researcher; the numbers are the point."""
    assert number_to_words("0.0837") == "zero point zero eight, three seven"
    assert number_to_words("82.1") == "eighty two point one"


def test_long_decimals_are_chunked() -> None:
    """Rule NUM-01b: a long digit run gets somewhere to breathe."""
    assert number_to_words("3.14") == "three point one four"  # short: read straight
    assert "," in number_to_words("3.14159")  # long: chunked


def test_rounded_fidelity_is_opt_in() -> None:
    rounded = number_to_words("0.0837", fidelity=NumericFidelity.ROUNDED, significant_figures=2)
    assert rounded == "zero point zero eight four"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("350 mAh/g", "three hundred and fifty milliamp hours per gram"),
        ("25 °C", "twenty five degrees Celsius"),
        ("82.1 %", "eighty two point one percent"),
        ("1 mA", "one milliamp"),  # singular
        ("2 mA", "two milliamps"),  # plural
        ("2.5 x 10^-3 mol", "two point five times ten to the power minus three moles"),
        ("1.4e6", "one point four times ten to the power six"),
        ("10-20 mA", "ten to twenty milliamps"),
        ("82.1 +/- 1.4 %", "eighty two point one plus or minus one point four percent"),
    ],
)
def test_numbers_with_units(text: str, expected: str) -> None:
    assert verbalize_numbers(text) == expected


def test_a_word_after_a_number_is_not_swallowed() -> None:
    """The unit pattern cannot know "350 cells" is not a unit until it looks it up, and
    dropping the word instead of putting it back deletes source text."""
    assert verbalize_numbers("0.05 and 1.50 V") == (
        "zero point zero five and one point five zero volts"
    )
    assert verbalize_numbers("500 cycles") == "five hundred cycles"
    assert verbalize_numbers("100 to 200 nm") == "one hundred to two hundred nanometres"


def test_designations_are_read_digit_by_digit() -> None:
    """NMC811 is a cathode, not eight hundred and eleven of something."""
    assert verbalize_numbers("NMC811") == "NMC eight one one"
    assert verbalize_numbers("the R2 metric") == "the R two metric"


def test_names_with_internal_digits_survive() -> None:
    assert "COVID" in verbalize_numbers("COVID-19 cases")
    assert verbalize_numbers("H2O") == "H two O"


@pytest.mark.parametrize(
    ("symbol", "spoken"),
    [
        ("mAh/g", "milliamp hours per gram"),
        ("mA", "milliamps"),
        ("µS/cm", "microsiemens per centimetre"),
        ("cm2", "square centimetres"),
        ("cm-1", "per centimetre"),
        ("mol/L", "moles per litre"),
        ("%", "percent"),
        ("ppm", "parts per million"),
    ],
)
def test_units(symbol: str, spoken: str) -> None:
    assert spoken_unit(symbol) == spoken


@pytest.mark.parametrize("symbol", ["C", "M", "T", "cells", "widgets"])
def test_ambiguous_and_non_units_are_not_units(symbol: str) -> None:
    """A bare C is a C-rate, coulombs or Celsius depending on the reader. Left as the letter."""
    assert spoken_unit(symbol) is None


# -- citations -------------------------------------------------------------------------------


def test_bracketed_citations_are_removed() -> None:
    assert verbalize_citations("as shown [12] in earlier work [1,2]") == "as shown in earlier work"


def test_author_year_citations_are_removed_by_default() -> None:
    text = "the crust forms (Peled, 1979; Winter et al., 2018) on first charge"
    assert verbalize_citations(text) == "the crust forms on first charge"


def test_attributed_mode_says_it_out_loud() -> None:
    out = verbalize_citations(
        "this contradicts (Jones, 2021)", verbosity=CitationVerbosity.ATTRIBUTED
    )
    assert "2021 study by Jones" in out


def test_identifiers_are_never_spoken() -> None:
    text = "see https://doi.org/10.1234/abc and arXiv:2401.12345 or mail a@b.com"
    out = verbalize_citations(text)
    assert "doi" not in out.lower()
    assert "arxiv" not in out.lower()
    assert "@" not in out


def test_cross_references_are_dropped() -> None:
    assert "Figure" not in verbalize_citations("the trend is clear as shown in Figure 4b here")


def test_superscript_citations_are_stripped_with_their_guards() -> None:
    text = "cold-start conditions4. Sold vehicles.1 Tesla leads. It was 5 cm2 wide. NMC811 cells."
    out = strip_superscript_citations(text)
    assert "conditions." in out and "conditions4" not in out
    assert "vehicles. Tesla" in out
    assert "cm2" in out  # a unit exponent, not a citation
    assert "NMC811" in out  # a designation ends in a capital


def test_superscript_stripping_needs_evidence() -> None:
    assert count_superscript_citations("a single stray7 digit") == 1
    assert count_superscript_citations("It was 5 cm2 wide") == 0


# -- parentheses -----------------------------------------------------------------------------


def test_acronym_definitions_become_appositives() -> None:
    out = verbalize_parentheticals("lithium-ion batteries (LIBs) age")
    assert out == "lithium-ion batteries, or LIBs, age"


def test_short_asides_become_appositives_and_long_ones_go() -> None:
    assert verbalize_parentheticals("the model (a boosted tree) failed") == (
        "the model, a boosted tree, failed"
    )
    long = "the model (which was trained on a very large dataset of many chemistries) failed"
    assert verbalize_parentheticals(long) == "the model failed"


# -- symbols ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected_fragment"),
    [
        ("τ is the time constant", "tau"),
        ("x ≈ 5", "approximately"),
        ("A → B", "leads to"),
        ("e.g. this", "for example"),
        ("Smith et al. showed", "and colleagues"),
        ("a ± b", "plus or minus"),
    ],
)
def test_symbols_become_words(text: str, expected_fragment: str) -> None:
    assert expected_fragment in verbalize_symbols(text)


def test_the_listener_lexicon_wins(profile: Profile) -> None:
    """Rule SYM-03: a domain term beats every default."""
    listener = Listener(lexicon={"SEI": "S E I", "NMC811": "N M C eight one one"})
    out = verbalize_text("The SEI on NMC811 grows.", profile, listener)
    assert "S E I" in out
    assert "N M C eight one one" in out


# -- the pipeline as a whole -----------------------------------------------------------------


def test_pipeline_order_survives_a_realistic_sentence(profile: Profile) -> None:
    text = (
        "The capacity loss was 0.0837 % per cycle over 500 cycles (see Fig. 4b), "
        "giving a retention of 82.1 ± 1.4 % [12,13]."
    )
    out = verbalize_text(text, profile)
    assert "zero point zero eight, three seven percent" in out
    assert "five hundred cycles" in out
    assert "eighty two point one plus or minus one point four percent" in out
    assert not any(c.isdigit() for c in out)
    assert "[" not in out and "(" not in out
