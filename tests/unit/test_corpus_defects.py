"""What twelve real papers did to the verbalizers.

Every case is a literal string from a PDF in the stress corpus. The two families between them
were 216 of 329 lint errors across the set:

* a diacritic emitted one position *before* the letter it belongs to;
* a citation run whose separators were extracted as spaces.
"""

from __future__ import annotations

import pytest

from mimem.config import Listener, load_profile
from mimem.verbalize import verbalize_text
from mimem.verbalize.citations import strip_superscript_citations
from mimem.verbalize.symbols import repair_diacritics

# -- diacritics that arrived early -------------------------------------------------------------


@pytest.mark.parametrize(
    ("broken", "expected"),
    [
        ("nine point nine zero ̊A", "nine point nine zero Å"),
        ("B. Hj ̈orvarsson, L. Douysset", "B. Hj örvarsson, L. Douysset"),
        ("H. D ̈urr, Organic Photochromism", "H. D ürr, Organic Photochromism"),
        ("C. Platzer-Bj ̈orkman", "C. Platzer-Bj örkman"),
    ],
)
def test_a_mark_before_its_letter_is_put_back(broken: str, expected: str) -> None:
    """PDF extraction emits the accent first, and it composes once it is moved."""
    assert repair_diacritics(broken) == expected


def test_the_angstrom_becomes_a_unit_again() -> None:
    """The best outcome of the repair: a recovered Å is a unit the lexicon can say."""
    spoken = verbalize_text("a = 9.90 ̊A", load_profile("study"), Listener())
    assert "̊" not in spoken
    assert spoken == "a equals nine point nine zero angstroms"


def test_a_mark_with_no_composable_base_is_dropped() -> None:
    """A macron over a crystallographic index whose digit is already a word: nothing to attach."""
    out = repair_diacritics("space group R ̄three c")
    assert "̄" not in out
    assert "three" in out


def test_ordinary_text_is_untouched() -> None:
    assert repair_diacritics("plain text with no marks") == "plain text with no marks"


#: Black square, parallel-to, up tack, asterisk operator, up and down arrows -- named by
#: code point rather than written out, because a source file full of look-alikes is exactly
#: what these tests are about.
FURNITURE_CODEPOINTS = (0x25A0, 0x2225, 0x22A5, 0x2217, 0x2191, 0x2193)


@pytest.mark.parametrize(
    "furniture",
    [
        f"{chr(0x25A0)}INTRODUCTION",
        f"Wang,{chr(0x2225)} and Cui",
        f"{chr(0x22A5)}These authors",
    ],
)
def test_page_furniture_characters_do_not_reach_the_audio(furniture: str) -> None:
    spoken = verbalize_text(furniture, load_profile("study"), Listener())
    assert all(chr(code) not in spoken for code in FURNITURE_CODEPOINTS)


def test_the_fraction_slash_is_a_fraction() -> None:
    text = f"one{chr(0x2044)}four of it"
    assert "over" in verbalize_text(text, load_profile("study"), Listener())


# -- citation runs separated by spaces ----------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "electrode materials.4 8 One such material",
        "than graphite.9 11 Unfortunately",
        "battery materials.19,21 23 So",
        "in weight.20,21 The water content",
        "a stable SEI.26,27 Significant research",
        "and Li21Si.1 At room temperature",
    ],
)
def test_a_citation_run_is_stripped_however_it_was_separated(text: str) -> None:
    """Superscript digits carry no punctuation, so whether the comma survives is the PDF's whim."""
    out = strip_superscript_citations(text)
    assert out != text
    assert not any(character.isdigit() for character in out.split(".")[-1][:4])


def test_an_acronym_ending_a_sentence_still_counts() -> None:
    """Requiring a *lower-case* letter before the stop cost thirty new failures on two papers.

    "a stable SEI.26,27 Significant" is a sentence ending exactly as a chemistry paper's
    sentences do, and it stopped being stripped.
    """
    assert (
        strip_superscript_citations("a stable SEI.26,27 Significant") == "a stable SEI. Significant"
    )


@pytest.mark.parametrize(
    "text",
    [
        "The value was 0.5 3 times higher",
        "It reached 12.5 in the second run",
        "Section 3.3 covers this",
        "measured 1.5 2 times",
    ],
)
def test_a_decimal_is_not_a_citation(text: str) -> None:
    """The point of a decimal is also a full stop to a regex; a letter in front tells them apart."""
    assert strip_superscript_citations(text) == text
