"""Sentences that lean on the one before them, and the boundaries that break them.

Rule SENT-02 was reporting nine warnings across the corpus and four of them were harmless: two
consecutive sentences of a paper, quoted in two consecutive beats, where the listener heard the
referent three seconds ago. The other five were real, and all five were boundaries the planner
had chosen -- a transition and a pause inserted between a pronoun and the thing it points at.
"""

from __future__ import annotations

import pytest

from mimem.config import Profile
from mimem.ir import BeatType, Script
from mimem.lint.script_rules import AnaphoraResolvesAcrossBeats
from mimem.verbalize.cohesion import unresolved_opening


@pytest.mark.parametrize(
    ("text", "word"),
    [
        ("This is apparent in the superior cycling of the cell.", "this"),
        ("They were directly mounted on the tightly closed ATR unit.", "they"),
        ("This would decrease the significance of side reactions.", "this"),
        ("The latter was measured at room temperature.", "the"),
        ("Such was the case for every sample.", "such"),
    ],
)
def test_a_sentence_that_points_at_the_one_before_it(text: str, word: str) -> None:
    assert unresolved_opening(text) == word


@pytest.mark.parametrize(
    "text",
    [
        # A demonstrative resolved by the noun that follows it.
        "This crust keeps growing at every cycle.",
        "These electrodes were cycled a hundred times.",
        # An expletive subject points at nothing, so nothing has been lost.
        "It is worth noting that the cell failed early.",
        "It turns out the binder was the problem.",
        # And an ordinary opening.
        "The clamping stress differs between the two resonators.",
    ],
)
def test_a_sentence_that_stands_on_its_own(text: str) -> None:
    assert unresolved_opening(text) is None


def _script(*runs: list[str]) -> Script:
    """A script whose segments hold the given beat texts, none of them generated."""
    from mimem.ir import Beat, Section, Segment, SourceMeta

    sections = [
        Section(
            id="s1",
            title="Results",
            order=1,
            segments=[
                Segment(
                    id=f"g{i}",
                    section_id="s1",
                    beats=[
                        Beat(
                            id=f"b{i}_{j}",
                            type=BeatType.EXPOSITION,
                            text=text,
                            generated=False,
                        )
                        for j, text in enumerate(run)
                    ],
                )
                for i, run in enumerate(runs)
            ],
        )
    ]
    return Script(doc_id="d", source=SourceMeta(format="pdf"), profile="study", sections=sections)


def test_two_quoted_sentences_in_a_row_are_not_a_defect() -> None:
    """The referent was spoken three seconds ago, and this is how the paper reads."""
    rule = AnaphoraResolvesAcrossBeats(Profile(name="study"))
    script = _script(
        [
            "Peaks were observed in one experiment and will be discussed in further detail.",
            "This makes it difficult to determine the origin of these species.",
        ]
    )
    assert rule.check(script) == []


def test_a_boundary_in_front_of_the_pronoun_is_a_defect() -> None:
    """Same two sentences, a segment boundary between them."""
    rule = AnaphoraResolvesAcrossBeats(Profile(name="study"))
    script = _script(
        ["Peaks were observed in one experiment and will be discussed in further detail."],
        ["This makes it difficult to determine the origin of these species."],
    )
    violations = rule.check(script)
    assert len(violations) == 1
    assert "'this'" in violations[0].message
