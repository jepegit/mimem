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


def test_the_same_font_maps_the_en_dash_onto_a_letter() -> None:
    """`2.7e4.2 V` is a voltage range, not scientific notation."""
    from mimem.clean.extraction import repair_dash_as_e
    from mimem.ir import Block, BlockKind, BlockRole, Document, SourceMeta

    thorn = chr(0x00FE)
    doc = Document(
        id="d",
        source=SourceMeta(format="pdf"),
        blocks=[
            Block(
                id="b1",
                kind=BlockKind.PARAGRAPH,
                role=BlockRole.BODY,
                text=f"Li/Li{thorn} and Ni3{thorn} and Mn2{thorn}: window of 2.7e4.2 V, 50e70 nm",
            )
        ],
    )
    assert repair_dash_as_e(doc) == 2
    assert "2.7 to 4.2 V" in doc.blocks[0].text
    assert "50 to 70 nm" in doc.blocks[0].text


def test_a_document_with_a_sound_font_keeps_its_scientific_notation() -> None:
    """`1.5e-9` must survive: rewriting an exponent would be worse than the bug being fixed."""
    from mimem.clean.extraction import repair_dash_as_e
    from mimem.ir import Block, BlockKind, BlockRole, Document, SourceMeta

    doc = Document(
        id="d",
        source=SourceMeta(format="pdf"),
        blocks=[
            Block(
                id="b1",
                kind=BlockKind.PARAGRAPH,
                role=BlockRole.BODY,
                text="a diffusivity of 1.5e-9 and a window of 2.7e4.2 V",
            )
        ],
    )
    assert repair_dash_as_e(doc) == 0
    assert "1.5e-9" in doc.blocks[0].text


def test_the_second_repair_still_knows_after_the_first_erased_the_evidence() -> None:
    """Recognising this font destroys what identifies it, and the repairs run far apart.

    The character swap happens early; the range repair has to wait until paragraph merging,
    because a range split across a column break is two fragments until then. Re-detecting at
    that point finds a clean document -- so the first repair leaves a diagnostic behind.
    """
    from mimem.clean.extraction import has_broken_math_font, repair_math_font
    from mimem.ir import Block, BlockKind, BlockRole, Document, SourceMeta

    thorn = chr(0x00FE)
    doc = Document(
        id="d",
        source=SourceMeta(format="pdf"),
        blocks=[
            Block(
                id="b1",
                kind=BlockKind.PARAGRAPH,
                role=BlockRole.BODY,
                text=f"Li/Li{thorn} and Ni3{thorn} and Mn2{thorn} were measured",
            )
        ],
    )
    assert repair_math_font(doc) > 0
    assert thorn not in doc.blocks[0].text, "the evidence is gone"
    assert has_broken_math_font(doc), "and the document still knows"


# -- reference markers the stripper walked past ------------------------------------------------
#
# All five shapes below reached the audio track of a real paper as bare numbers, and all five
# came from a document ``uses_superscript_citations`` had already recognised: the paper was
# known to cite this way, and the markers were left in anyway.


def _spoken(text: str) -> str:
    return verbalize_text(text, load_profile("study"), Listener(), strip_superscripts=True)


@pytest.mark.parametrize(
    ("written", "spoken"),
    [
        # A marker at the end of a clause rather than a sentence: a full stop follows it, not a
        # capital letter. Webb et al.
        (
            "lithiation of native oxide layer on the electrodes.52-55.",
            "lithiation of native oxide layer on the electrodes.",
        ),
        # ...or a lower-case word.
        (
            "oxide layer on the electrodes.52-55 in one line",
            "oxide layer on the electrodes. In one line",
        ),
        # A marker welded to a unit symbol. Two digits, so it is not an exponent. Irisarri et al.
        (
            "sheets from 3.8 Å to ca. 4.15 Å44 while the second",
            "sheets from three point eight angstroms to ca. four point one five angstroms "
            "while the second",
        ),
        # A marker after a closing bracket. Nie and Lucht, four times over.
        (
            "lithium ethylene dicarbonate (LEDC).31 The SEI predominantly contains",
            "lithium ethylene dicarbonate, or LEDC. The SEI predominantly contains",
        ),
        # A marker after a parenthetical cross-reference, which only becomes visible once the
        # reference is deleted and the space it left behind has been closed up.
        (
            "are similar to those of fresh electrodes (see Figure 5).54 Such findings",
            "are similar to those of fresh electrodes. Such findings",
        ),
    ],
)
def test_a_reference_marker_does_not_reach_the_audio(written: str, spoken: str) -> None:
    assert _spoken(written) == spoken


@pytest.mark.parametrize(
    ("written", "spoken"),
    [
        # A unit exponent is a single digit, and stays one.
        ("an area of 12 cm2", "an area of twelve square centimetres"),
        ("a volume of 4 cm3", "a volume of four cubic centimetres"),
        # A designation is not a citation, whatever follows it.
        ("the cathode NMC811", "the cathode NMC eight one one"),
        ("the salt LiFePO4", "the salt LiFePO four"),
        # A cross-reference has a space in it and a marker never does, which is the whole reason
        # the lookahead could be dropped from the after-a-stop pattern.
        ("Fig. 3 shows it again.", "The figure shows it again."),
        # A decimal point is a full stop to a regex, but it has a digit in front of it.
        ("a capacity of 0.5 3 times over", "a capacity of zero point five three times over"),
        # The subscripts of a non-stoichiometric formula. "LiNi." is a letter and a stop and
        # "5" is a run, so dropping the lookahead from the after-a-stop pattern ate all three
        # -- in the one corpus paper that is named after this cathode. A digit welded to the
        # letter that follows it is a subscript, never a marker.
        (
            "a full cell of LiNi.5Co.2Mn.3O2 and silicon-graphite",
            "a full cell of lithium nickel zero point five cobalt zero point two manganese "
            "zero point three oxygen two and silicon-graphite",
        ),
    ],
)
def test_a_number_that_is_not_a_reference_marker_survives(written: str, spoken: str) -> None:
    assert _spoken(written) == spoken


def test_a_parenthetical_cross_reference_takes_its_bracket_with_it() -> None:
    """ "(see Figure 1a)" left the word "see" behind, and a sentence ended on it.

    The pattern began at "Figure", so the deletion left "(see " for the punctuation tidy-up to
    reduce to "the interlayer distance see." -- in every paper that uses the parenthetical
    aside, which is most of them.
    """
    from mimem.verbalize.citations import verbalize_citations

    assert (
        verbalize_citations("the interlayer distance (see Figure 1a). If crosslinking")
        == "the interlayer distance. If crosslinking"
    )


def test_a_marker_is_still_only_stripped_where_the_paper_cites_that_way() -> None:
    """The gate has not moved: one stray digit after a word is a typo, not a house style."""
    from mimem.verbalize.citations import MIN_SUPERSCRIPT_EVIDENCE, count_superscript_citations

    assert count_superscript_citations("we measured conditions4 and stopped") == 1
    assert MIN_SUPERSCRIPT_EVIDENCE > 1


# -- a glyph with no meaning, and a table numbered the other way --------------------------------


@pytest.mark.parametrize(
    ("written", "spoken"),
    [
        # ACS puts the double bond of a carbonyl in the private use area, so "O-(C=O)-O"
        # arrives with a character no speech engine has anything to say about. Eight TTS-01
        # errors in one paper, all of them this.
        (
            "species containing C-O and O-(CO)-O bonds",
            "species containing C-O and O-, C O,-O bonds",
        ),
        # ...and an em dash, in another paper's title.
        (
            "Effects of InhomogeneitiesNanoscale to Mesoscaleon the Durability",
            "Effects of Inhomogeneities Nanoscale to Mesoscale on the Durability",
        ),
    ],
)
def test_a_private_use_character_never_reaches_the_speech_engine(written: str, spoken: str) -> None:
    assert _spoken(written) == spoken


@pytest.mark.parametrize(
    ("written", "spoken"),
    [
        # Most journals number their tables in Roman, and the pattern only knew Arabic. Five of
        # one paper's eight STR-08 errors were the Roman half.
        (
            "pyrolysis of sugar do confirm this trend (see Table II). Moreover, the increase",
            "pyrolysis of sugar do confirm this trend. Moreover, the increase",
        ),
        (
            "differences in electrochemical performance (see Table I). The large differences",
            "differences in electrochemical performance. The large differences",
        ),
        # A reference with no number left at all -- and, in one paper, promoted into a concept:
        # "What did they report for see Figure?"
        (
            "the trend continues, see Figure, and the capacity fades",
            "the trend continues, and the capacity fades",
        ),
        # Deleting both halves of a coordination used to leave the coordinator behind.
        ("the results are given in Table III and Figure 4.", "the results are."),
    ],
)
def test_a_cross_reference_the_listener_cannot_follow_is_removed(written: str, spoken: str) -> None:
    assert _spoken(written) == spoken


@pytest.mark.parametrize(
    "text",
    [
        # A bare Roman numeral is never a table: the label has to come first.
        "I show that the capacity fades.",
        # "see" on its own is an ordinary verb.
        "we see clear evidence of lithiation",
        # And an ordinary coordination keeps its coordinator.
        "we tested cells and modules, then stopped.",
        "lithium and sodium were compared.",
    ],
)
def test_the_words_a_cross_reference_is_made_of_still_work_as_words(text: str) -> None:
    assert _spoken(text) == text
