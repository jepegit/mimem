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


# -- a maths font mapped onto Icelandic letters -------------------------------------------------


def test_the_ion_gets_its_charge_back() -> None:
    """`Li/Liþ` is `Li/Li+`: an Elsevier maths font mis-mapped on the way out of the PDF."""
    from mimem.clean.extraction import MATH_FONT

    assert MATH_FONT[chr(0x00FE)] == "+"
    assert MATH_FONT[chr(0x00F0)] == "("
    assert MATH_FONT[chr(0x00DE)] == ")"


def test_the_repair_waits_for_evidence() -> None:
    """One thorn in a document is a name; a hundred against digits is a broken font.

    Gated like the superscript-citation rule and for the same reason -- a repair that fires on
    one ambiguous character is worse than one that waits for a pattern. Of twelve corpus papers,
    three showed the pattern and one had a single legitimate thorn, which is left alone.
    """
    from mimem.clean.extraction import uses_broken_math_font
    from mimem.ir import Block, BlockKind, BlockRole, Document, SourceMeta

    def doc(text: str) -> Document:
        return Document(
            id="d",
            source=SourceMeta(format="pdf"),
            blocks=[Block(id="b1", kind=BlockKind.PARAGRAPH, role=BlockRole.BODY, text=text)],
        )

    broken = f"Li/Li{chr(0x00FE)} and Ni3{chr(0x00FE)} and Mn2{chr(0x00FE)} were measured"
    assert uses_broken_math_font(doc(broken))
    assert not uses_broken_math_font(doc("Halldór wrote það in Icelandic"))


# -- blocks that are not prose ------------------------------------------------------------------


@pytest.mark.parametrize(
    "not_prose",
    [
        "Manuscript submitted September 9, 2003; revised manuscript received June 1",
        "Li~1! 12a 0.375 0 0.25 Li~2! 48e 0.118~1! 0.156~1! 0.961~1! Si 16c 0.75",
        "h i g h l i g h t s",
        "Sample Ar flow rate (cc/min) Reaction yield (%) BET (m2/g) 1 2 3",
        "0 600 1200 1800 2400 3000 3600 4200",
        "Solar Energy Materials & Solar Cells 95 (2011) 3596-3599 journal homepage",
    ],
)
def test_a_block_with_no_function_words_is_not_narrated(not_prose: str) -> None:
    """Contents pages, axis labels, crystallographic tables and journal front matter.

    The signal is function words rather than digits: a unit-cell table is only 20% numerals, so
    a numeric-density test misses it, while what it shares with a 98%-full-stop contents page is
    that nothing in either is doing grammatical work.
    """
    from mimem.triage.rules import reads_as_prose

    assert not reads_as_prose(not_prose)


@pytest.mark.parametrize(
    "prose",
    [
        "Although silicon has the highest theoretical specific energy density of any material",
        "Structural Changes in Silicon Anodes during Lithium Insertion",
        "XRD patterns were collected using a Siemens model Kristalloflex diffractometer",
        "Nano Letters",
        "We show that a paired reference resonator reproduces the thermal drift",
    ],
)
def test_real_prose_and_short_headings_survive(prose: str) -> None:
    from mimem.triage.rules import reads_as_prose

    assert reads_as_prose(prose)
