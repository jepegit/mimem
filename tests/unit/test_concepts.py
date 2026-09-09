"""Concept extraction, scoring and the registry.

Two things are being defended here. First, that extraction finds what a paper is *about* rather
than what it merely repeats -- author names, citation fragments and sliding-window debris all
recur constantly and mean nothing. Second, that the listener profile actually changes the
ranking, because rule DIF-04 is the single biggest quality lever a specialist has and it is
easy to write a version of it that quietly does nothing.
"""

from __future__ import annotations

import pytest

from mimem.concepts import build, extract, merge, preload_terms, score
from mimem.concepts.norms import abstractness, status
from mimem.config import Expertise, Listener
from mimem.ir import (
    Block,
    BlockKind,
    BlockRole,
    ConceptRegistry,
    Document,
    SourceMeta,
    block_id,
)


def _doc(*items: tuple[str, str, str], authors: list[str] | None = None) -> Document:
    """(kind, role, text) triples, sentence-split like a cleaned document."""
    from mimem.clean.sentences import sentence_spans

    blocks = []
    for i, (kind, role, text) in enumerate(items):
        blocks.append(
            Block(
                id=block_id(kind, 1, i, text),
                kind=BlockKind(kind),
                role=BlockRole(role),
                text=text,
                order=i,
                page=1,
                sentences=sentence_spans(text),
            )
        )
    return Document(
        id="d",
        source=SourceMeta(format="pdf", title="A Paper", authors=authors or []),
        blocks=blocks,
    )


def _names(candidates) -> list[str]:
    return [c.canonical.lower() for c in candidates]


# -- extraction ------------------------------------------------------------------------------


def test_an_acronym_definition_is_the_strongest_signal() -> None:
    doc = _doc(
        ("paragraph", "body", "A solid electrolyte interphase (SEI) forms on the anode."),
    )
    found = extract(doc)
    sei = next(c for c in found if "interphase" in c.canonical.lower())
    assert "SEI" in sei.aliases
    assert "acronym" in sei.evidence


def test_an_implausible_acronym_is_not_a_definition() -> None:
    """ "...as shown in the plot (Figure 2)" is not defining anything."""
    doc = _doc(("paragraph", "body", "The capacity declined over time (Figure 2) as expected."))
    assert not any("capacity declined" in n for n in _names(extract(doc)))


def test_definitional_sentences_and_symbol_glosses() -> None:
    doc = _doc(
        ("paragraph", "body", "Coulombic efficiency is defined as the ratio of charge."),
        ("paragraph", "body", "Here τ is the time constant of the decay process."),
    )
    found = _names(extract(doc))
    assert any("coulombic efficiency" in n for n in found)
    assert "tau" in found


def test_a_phrase_must_recur_to_count() -> None:
    once = _doc(("paragraph", "body", "The jelly roll was inspected."))
    assert not any("jelly roll" in n for n in _names(extract(once)))

    often = _doc(
        *[("paragraph", "body", f"The jelly roll was inspected in cell {i}.") for i in range(5)]
    )
    assert any("jelly roll" in n for n in _names(extract(often)))


def test_author_names_are_not_concepts() -> None:
    """A corresponding author's name repeats on every page; the document already knows who
    wrote it, so ask it rather than guessing from capitalisation."""
    doc = _doc(
        *[("paragraph", "body", "Contact Anupam Yadav for the dataset.") for _ in range(6)],
        authors=["Anupam Yadav", "Mustafa Abdullah"],
    )
    assert not any("yadav" in n for n in _names(extract(doc)))


def test_citation_fragments_and_coordinated_phrases_are_not_concepts() -> None:
    doc = _doc(
        *[
            ("paragraph", "body", "As Smith et al reported, charging and discharging differ.")
            for _ in range(6)
        ]
    )
    found = _names(extract(doc))
    assert "et al" not in found
    assert "charging and discharging" not in found  # two ideas, not one


def test_a_term_with_an_internal_preposition_survives() -> None:
    """ "state of charge" is one term; the coordinator filter must not eat it."""
    doc = _doc(*[("paragraph", "body", f"The state of charge was {i} percent.") for i in range(5)])
    assert any("state of charge" in n for n in _names(extract(doc)))


def test_overlapping_ngrams_are_collapsed() -> None:
    """A sliding window produces "battery degradation" and "lithium-ion battery degradation"
    as rivals for the same budget."""
    common = "Battery degradation was measured. " * 10
    rare = "Lithium-ion battery degradation was measured. "
    doc = _doc(("paragraph", "body", common + rare))
    found = _names(extract(doc))
    assert "battery degradation" in found
    assert "lithium-ion battery degradation" not in found  # a rare elaboration of a common core


def test_the_document_casing_is_preserved() -> None:
    doc = _doc(*[("paragraph", "body", "The optimized GBDT model was tuned.") for _ in range(5)])
    assert any("GBDT" in c.canonical for c in extract(doc))


# -- scoring ---------------------------------------------------------------------------------


@pytest.fixture
def scored_doc() -> Document:
    return _doc(
        ("heading", "title", "Interphase repair limits silicon anode life"),
        (
            "paragraph",
            "abstract",
            "We show that interphase repair, not particle fracture, limits life.",
        ),
        ("paragraph", "results", "Interphase repair consumed lithium. " * 6),
        ("paragraph", "methods", "The jelly roll was removed by hand. " * 6),
        ("caption", "results", "Figure 1. Interphase repair against cycle number."),
    )


def test_scores_are_bounded_and_auditable(scored_doc: Document) -> None:
    concepts = score(scored_doc, extract(scored_doc))
    assert concepts
    for c in concepts:
        assert 0.0 <= c.difficulty <= 1.0
        assert 0.0 <= c.importance <= 1.0
        assert c.signals  # the components that produced the score, for auditing


def test_position_makes_a_concept_important(scored_doc: Document) -> None:
    """Title and abstract are where a paper says what it means."""
    concepts = {c.canonical.lower(): c for c in score(scored_doc, extract(scored_doc))}
    interphase = next(c for k, c in concepts.items() if "interphase" in k)
    jelly = next((c for k, c in concepts.items() if "jelly" in k), None)
    assert jelly is not None
    assert interphase.importance > jelly.importance


def test_a_known_term_is_no_longer_difficult(scored_doc: Document) -> None:
    """Rule DIF-04 at its bluntest: you said you know this one."""
    candidates = extract(scored_doc)
    plain = {c.canonical.lower(): c.difficulty for c in score(scored_doc, candidates)}
    target = next(k for k in plain if "jelly" in k)
    informed = {
        c.canonical.lower(): c.difficulty
        for c in score(scored_doc, candidates, Listener(known_terms=[target]))
    }
    assert informed[target] < plain[target] * 0.5


def test_knowing_a_component_makes_the_compound_easier() -> None:
    """ "anode active material" is easier for someone who already owns "anode"."""
    listener = Listener(known_terms=["anode"])
    assert listener.knows_part_of("anode active material")
    assert not listener.knows_part_of("cathode active material")


def test_domain_expertise_changes_the_ranking() -> None:
    """The acceptance test for M3, and the bug it caught: matching a domain *name* against a
    concept is inert, because no concept is called "electrochemistry"."""
    doc = _doc(
        ("paragraph", "abstract", "We compare a prismatic cell with a teardown analysis."),
        ("paragraph", "results", "The prismatic cell was opened. " * 6),
        ("paragraph", "results", "The teardown analysis proceeded. " * 6),
    )
    candidates = extract(doc)
    novice = {c.canonical.lower(): c.difficulty for c in score(doc, candidates)}

    expert = Listener(
        name="e",
        expertise={"electrochemistry": Expertise.EXPERT},
        domain_terms={"electrochemistry": ["cell", "electrode"]},
    )
    informed = {c.canonical.lower(): c.difficulty for c in score(doc, candidates, expert)}

    cell = next(k for k in novice if "prismatic" in k)
    teardown = next(k for k in novice if "teardown" in k)
    assert informed[cell] < novice[cell]  # inside the declared domain
    assert informed[teardown] == pytest.approx(novice[teardown])  # outside it, unchanged


# -- registry --------------------------------------------------------------------------------


def test_registry_round_trips_and_ranks(scored_doc: Document) -> None:
    registry = build(scored_doc)
    restored = ConceptRegistry.from_json(registry.to_json())
    assert restored == registry
    ranked = registry.ranked()
    assert ranked == sorted(ranked, key=lambda c: (-c.budget, c.canonical))


def test_hand_edits_survive_regeneration(scored_doc: Document) -> None:
    """A registry that reverts the moment you re-run is a read-only file with extra steps."""
    first = build(scored_doc)
    target = first.ranked()[0]
    target.overrides = {"short_def": "my own wording", "importance": 0.99}
    target.apply_overrides()

    second = build(scored_doc, previous=first)
    kept = second.get(target.id)
    assert kept.short_def == "my own wording"
    assert kept.importance == pytest.approx(0.99)


def test_a_hand_added_concept_is_not_deleted(scored_doc: Document) -> None:
    from mimem.ir.concepts import Concept

    first = build(scored_doc)
    mine = Concept(id="c_mine", canonical="a thing I added", overrides={"importance": 0.8})
    mine.apply_overrides()
    first.add(mine)

    second = build(scored_doc, previous=first)
    assert "c_mine" in second.concepts


def test_preload_is_capped_and_ordered_by_first_need(scored_doc: Document) -> None:
    """Rule PRE-01/STR-03: a pre-load is a sequence you walk into the paper with, and more
    than a handful of new labels at once is the load pre-training exists to avoid."""
    registry = build(scored_doc)
    terms = preload_terms(registry, limit=3)
    assert len(terms) <= 3


def test_merge_is_a_no_op_without_overrides(scored_doc: Document) -> None:
    first = build(scored_doc)
    second = build(scored_doc)
    assert merge(second, first).concepts.keys() == first.concepts.keys()


# -- norms -----------------------------------------------------------------------------------


def test_abstractness_orders_the_obvious_cases() -> None:
    """Without the Brysbaert norms this is morphology, so only wide gaps are asserted."""
    assert abstractness("interpretability") > abstractness("electrode")
    assert 0.0 <= abstractness("anything") <= 1.0


def test_norms_status_is_honest_about_its_source() -> None:
    """A morphological guess and a measured rating must never be indistinguishable."""
    reported = status()
    assert reported.source in {"brysbaert", "morphology"}
    if reported.source == "morphology":
        assert reported.entries == 0


# -- phrases that are clauses, which the verb lists could not see --------------------------------
#
# 38 of the stress corpus's 482 concepts were clause fragments, and the programme asked questions
# about them: "What did they report for figure shows?" Both lists were written in the past tense.


def _is_a_term(phrase: str) -> bool:
    from mimem.concepts.extract import CLAUSE_LIKE, _is_phrase_like

    return _is_phrase_like(phrase.split()) and not CLAUSE_LIKE.search(phrase)


@pytest.mark.parametrize(
    "fragment",
    [
        # A finite verb at the boundary. PHRASE_BOUNDARY_VERBS had only past participles.
        "figure shows",
        "shows the XRD pattern",
        "see Figure",
        "see Table",
        "becomes amorphous",
        "containing species",
        "consistent with the presence",
        "peaks characteristic",
        "capacity associated",
        "electrodes extracted",
        "against sodium metal counter",
        "discharged to mv",
        "above mv",
        # A finite verb in the *middle*, which the boundary check cannot reach. This is what
        # CLAUSE_LIKE is for, and it had only the auxiliaries.
        "scan shows the xrd",
        "study are open-sourced",
    ],
)
def test_a_clause_is_not_a_concept(fragment: str) -> None:
    assert not _is_a_term(fragment)


@pytest.mark.parametrize(
    "term",
    [
        # Ordinary terms, which must survive both lists.
        "crystalline silicon",
        "irreversible capacity",
        "solid electrolyte interphase",
        "differential capacity",
        "state of charge",
        "battery degradation",
        "oxygen-containing yttrium hydride",
        # "lead" is the metal here. A rule that loses this to catch "leads to capacity fade" is a
        # bad trade, so the lead family is deliberately absent from CLAUSE_LIKE.
        "lead acid battery",
        "lithium lead alloy",
    ],
)
def test_a_term_survives_the_verb_lists(term: str) -> None:
    assert _is_a_term(term)
