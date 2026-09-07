"""Definitions taken from the paper's own sentences (rules STR-03, GRD-01).

Nearly every test here is a sentence that *looked* like a definition and was not. That is the
shape of this problem: matching "X is Y" is trivial and wrong, and the module is almost entirely
the guards that came off two real documents. Each case below is one of those, kept so the guard
that stopped it cannot quietly come off.
"""

from __future__ import annotations

import pytest

from mimem.concepts import definitions
from mimem.concepts.definitions import acceptable, bracketed_ok


def _found(term: str, sentence: str) -> str | None:
    hit = definitions._from_sentence(term, sentence)
    return hit[0] if hit else None


# -- what it should find ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("term", "sentence", "expected"),
    [
        (
            "resonator",
            "A resonator is a mechanical structure that vibrates at a fixed frequency.",
            "a mechanical structure that vibrates at a fixed frequency",
        ),
        (
            "acoustic emission",
            "Acoustic emission refers to the transient elastic waves released by cracking.",
            "the transient elastic waves released by cracking",
        ),
        (
            "drift",
            "Thermal drift is defined as the frequency change per kelvin of substrate.",
            "the frequency change per kelvin of substrate",
        ),
        (
            "SEI",
            "The SEI (a passivating layer that forms on the anode) limits further reduction.",
            "a passivating layer that forms on the anode",
        ),
        (
            "reference resonator",
            "The reference resonator is mechanically decoupled from the structure under test.",
            "mechanically decoupled from the structure under test",
        ),
        (
            "interphase",
            "The interphase, which is a thin film of decomposition products, passivates it.",
            "a thin film of decomposition products",
        ),
    ],
)
def test_it_finds_the_definition_the_author_wrote(term: str, sentence: str, expected: str) -> None:
    assert _found(term, sentence) == expected


def test_the_trailing_stop_is_removed() -> None:
    """The pre-load template supplies its own punctuation; two stops reach the audio track."""
    assert not (
        _found("resonator", "A resonator is a device that vibrates freely.") or ""
    ).endswith(".")


# -- what it must not find -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("term", "sentence", "why"),
    [
        (
            "residual",
            "The residual is far larger than the measurement noise floor.",
            "a comparison is a result, not a definition",
        ),
        (
            "drift coefficient",
            "The mean drift coefficient was 0.0142 %/K with a standard deviation of 0.0009.",
            "a measurement is not a definition",
        ),
        (
            "heat generation",
            "Heat generation is the cause of peak temperatures exceeding 800 degrees.",
            "a definition carrying a value belongs to NUM-01, not to the pre-load",
        ),
        (
            "thermal drift",
            "Keywords: thermal drift, resonant strain sensor, compensation network",
            "the next item in a comma-separated list is not a definition of the previous one",
        ),
        (
            "lithium-ion batteries",
            "As lithium-ion batteries are widely deployed, thermal runaway poses safety risks.",
            "the plural copula without a determiner swallows the whole clause",
        ),
        (
            "application scenarios",
            "We survey application scenarios, including early electro-thermal signal warning.",
            "a list continuation is not a definition",
        ),
        (
            "lithium-ion batteries",
            "Lithium-ion batteries, owing to their high energy density, dominate the market.",
            "an adverbial appositive says why, not what",
        ),
        (
            "TR warning",
            "We present TR warning, following a logical framework of data and models.",
            "a present participle describes a circumstance, not the thing",
        ),
        (
            "resonator",
            "A resonator is a resonator that has been tuned to a particular frequency.",
            "circular: the definition restates the term",
        ),
        (
            "network",
            "The compensation network is passive and occupies half a square millimetre.",
            "a property claim without a determiner is not a classification",
        ),
    ],
)
def test_it_refuses_what_only_looks_like_a_definition(term: str, sentence: str, why: str) -> None:
    assert _found(term, sentence) is None, why


def test_a_definition_is_a_phrase_not_a_paragraph() -> None:
    long_tail = " ".join(["word"] * 40)
    assert _found("thing", f"A thing is a {long_tail}.") is None
    assert _found("thing", "A thing is a bit.") is None  # ...and not two words either


def test_the_term_must_actually_be_in_the_sentence() -> None:
    assert _found("resonator", "The device is a mechanical structure that vibrates.") is None


# -- the guards, directly --------------------------------------------------------------------


def test_a_bare_noun_phrase_is_a_list_item_not_an_appositive() -> None:
    assert not bracketed_ok("resonant strain sensor")
    assert bracketed_ok("a passivating layer")
    assert bracketed_ok("held mechanically free on the same die")


def test_an_empty_head_defines_nothing() -> None:
    assert not acceptable("resonator", "one of the two devices used")


# -- end to end ------------------------------------------------------------------------------


def test_a_document_gets_its_terms_defined(markdown_file) -> None:  # type: ignore[no-untyped-def]
    """The whole point: a build with no model still establishes terms (rule STR-03)."""
    from mimem.clean import clean
    from mimem.ingest import load

    doc = clean(load(markdown_file))
    found = definitions.find(doc, ["resonator", "widget"])
    assert all(d.span.block_id for d in found.values()), "GRD-01: every gloss points at a block"


def test_the_first_definition_wins() -> None:
    """A paper introduces a term where it first needs it."""
    from mimem.ir import Block, BlockKind, BlockRole, Document, SourceMeta

    blocks = [
        Block(
            id=f"b{i}",
            kind=BlockKind.PARAGRAPH,
            role=BlockRole.INTRODUCTION,
            text=text,
            page=1,
        )
        for i, text in enumerate(
            [
                "A resonator is a device that vibrates at a fixed frequency.",
                "A resonator is a completely different thing said later on.",
            ]
        )
    ]
    doc = Document(id="d", source=SourceMeta(format="markdown"), blocks=blocks)
    found = definitions.find(doc, ["resonator"])
    assert found["resonator"].text == "a device that vibrates at a fixed frequency"
    assert found["resonator"].span.block_id == "b0"
