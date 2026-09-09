"""Sentences that only work when you have just heard the one before (rule SENT-02).

"This is apparent in the superior cycling of the cell" is a perfectly good sentence in a paper,
where the reader's eye can go back one line. Spoken, it depends entirely on what was said
immediately before it -- so whether it is a defect is not a property of the sentence at all, but
of what the programme puts in front of it.

That is why this lives here rather than inside the lint rule: the planner needs the same
judgement when it chooses where to cut a segment, and a boundary placed in front of one of these
is what turns a quoted sentence into a broken one.
"""

from __future__ import annotations

import re

#: Bare pronouns and demonstratives. A demonstrative followed by a noun ("this crust") is
#: resolved by the noun and is not matched -- see :data:`BARE`.
_PRONOUNS = r"it|this|that|these|those|they|them|such"

#: "It is worth noting", "it turns out", "there is no" -- the subject is grammatical filler and
#: points at nothing, so there is nothing for the listener to have lost.
EXPLETIVE = re.compile(
    r"^it\s+(?:is|was|turns\s+out|follows|remains|seems|appears|takes|helps|matters)\b",
    re.IGNORECASE,
)

#: A demonstrative counts as unresolved only when nothing follows it that could be the referent:
#: "this is why" (bare) fails, "this repair" (determiner) passes.
BARE = re.compile(
    r"^(?:" + _PRONOUNS + r")\s+(?:is|are|was|were|means|meant|gives|gave|shows|showed|gets|"
    r"got|makes|made|gains|has|have|had|does|do|did|can|could|will|would|"
    r"happens|explains|becomes|became|comes|came|goes|went|stays|stayed|leaves|"
    r"left|costs|cost|matters|mattered|then|also|too|in|on|at|by|for|with|and|but|so)\b",
    re.IGNORECASE,
)

#: These two never resolve out loud whatever follows them, so they are matched on their own.
ALWAYS = re.compile(r"^the\s+(?:former|latter|above|aforementioned)\b", re.IGNORECASE)


def unresolved_opening(text: str) -> str | None:
    """The word this text leans on, or ``None`` if it stands on its own.

    >>> unresolved_opening("This is apparent in the superior cycling")
    'this'
    >>> unresolved_opening("This crust keeps growing") is None
    True
    >>> unresolved_opening("It is worth noting that the cell failed") is None
    True
    """
    opening = text.strip()
    if not opening or EXPLETIVE.match(opening):
        return None
    match = ALWAYS.match(opening) or BARE.match(opening)
    return match.group(0).split()[0].lower() if match else None
