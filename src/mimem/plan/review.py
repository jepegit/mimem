"""The closing review block: every section's questions, shuffled together.

Rule ``STR-07`` asks for a review block whose items are interleaved so that no two consecutive
questions come from the same section, and rule ``SPC-04`` confines interleaving to exactly here.
That pairing is not arbitrary. The knowledge base is blunt about it (§1.4): interleaving helps
when the skill is *telling things apart*, and the meta-analytic estimate for expository text is
0.21 and not significant -- so interleaving the exposition would be applying a null result to
the part of the programme that carries the argument. In a review block, where the listener has
to retrieve without the context of the surrounding section, it is doing the thing it is good at.

The ordering is the classic greedy: always take the section with the most questions left that
is not the section you just used. That is optimal whenever an interleaved order exists at all.
When one section has more questions than all the others put together, no order satisfies the
rule; :func:`interleave` places the remainder rather than dropping questions, and returns how
many adjacencies it could not avoid so the caller can report it instead of hiding it.
"""

from __future__ import annotations

from collections import defaultdict

from mimem.ir import Card


def interleave(cards: list[Card]) -> tuple[list[Card], int]:
    """Order ``cards`` so consecutive items come from different sections (rule STR-07).

    Returns the ordering and the number of same-section adjacencies that were unavoidable.
    """
    if len(cards) < 2:
        return list(cards), 0

    groups: dict[str, list[Card]] = defaultdict(list)
    for card in cards:
        groups[card.section_id or ""].append(card)

    out: list[Card] = []
    previous: str | None = None
    collisions = 0

    while any(groups.values()):
        # Most-remaining-first, avoiding the section just used; ties broken by section id so
        # that the same input always produces the same review block.
        options = sorted(
            (key for key, items in groups.items() if items),
            key=lambda k: (-len(groups[k]), k),
        )
        pick = next((k for k in options if k != previous), None)
        if pick is None:
            pick = options[0]
            collisions += 1
        out.append(groups[pick].pop(0))
        previous = pick

    return out, collisions
