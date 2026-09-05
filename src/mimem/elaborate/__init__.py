"""Stage 6: spending the elaboration budget.

Rule ``DIF-02`` says the budget for a concept is a function of ``difficulty x importance`` and
gives the order it is spent in: gloss, then concrete anchor, then the elaborative "why", then a
worked example, then an analogy, then extra repetition, then an extra retrieval item. The last
two are the planner's; the first four are here.

The order is the design. A listener who gets an anchor for an idea nobody explained has been
given a picture of nothing, and an analogy for an idea they already understand is a tax on their
attention. So the budget is spent depth-first per concept, hardest and most central first, and
it runs out where it runs out.
"""

from mimem.elaborate.run import (
    Degradation,
    ElaborationReport,
    elaborate,
    plan_requests,
)

__all__ = ["Degradation", "ElaborationReport", "elaborate", "plan_requests"]
