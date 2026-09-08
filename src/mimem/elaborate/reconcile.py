"""Two implementations of the same task, and which one the programme uses.

Until now the deterministic path was a *fallback*: it ran when the model was absent or its
answer was rejected. That framing hid something the definitions work made obvious. When both
implementations exist, the deterministic one is not a lesser substitute -- it is the **control**,
and often the more precise of the two.

The worked example is glosses. The deterministic finder takes definitions from the paper's own
sentences and finds one or two per document with near-perfect precision, because every guard in
it came off a case where a plausible match was wrong. A model would find ten with unknown
precision. Whichever you would rather have, it is plainly not true that one is the fallback for
the other, and the design should stop saying so.

So each task carries a mode:

``off``
    The deterministic path only. The model is never called. This is ``--local``, and the default
    for a task whose rules are trusted.

``assist``
    The deterministic path runs first. The model is called **only for what the rules did not
    answer**, which is where a model earns its cost: recall, not precision.

``prefer``
    The model runs first and its answer is used if it passes the grounding gate; the
    deterministic path catches what is left. For tasks the rules cannot do at all -- an analogy,
    an anchor, a figure description -- there is nothing to reconcile and this is the only
    sensible mode.

**A deviation from ``docs/PLAN-ai.md`` worth flagging.** The plan says ``assist`` runs *both*
paths always, so that every paid run yields a free paired comparison. That would call the model
and then throw the answer away whenever the rules already had one, which is a real cost for a
comparison that ``mimem compare`` produces better anyway -- by building the whole document twice
and diffing the artefacts, rather than by inferring from a task-level log. So ``assist`` skips
the call it would discard, and the comparison lives in the command built for it.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum


class Mode(StrEnum):
    """How a task's two implementations divide the work."""

    OFF = "off"
    ASSIST = "assist"
    PREFER = "prefer"


class Absence(StrEnum):
    """Why a task has no model answer.

    Four different things were one thing until now, all of them reported as "degraded". They
    need four different sentences because they need four different actions: set a key, start a
    server, choose another model, raise the cap. A user who cannot tell "you have no key" from
    "the server timed out" cannot fix either.
    """

    #: No provider is configured at all. ``--local``, or a forgotten key.
    NOT_CONFIGURED = "not configured"
    #: A provider is configured but did not answer: network, or a server that is not running.
    UNREACHABLE = "unreachable"
    #: It answered, but not with something the schema accepts.
    REFUSED = "refused"
    #: It answered well-formed and the grounding gate rejected the content. **Not a failure** --
    #: this is the system working, and the only one of these that is about the document rather
    #: than the setup.
    REJECTED = "rejected"
    #: The budget cap stopped the run.
    OVER_BUDGET = "over budget"

    @property
    def is_setup(self) -> bool:
        """Would configuring something differently have avoided this?"""
        return self in {Absence.NOT_CONFIGURED, Absence.UNREACHABLE, Absence.OVER_BUDGET}

    @property
    def advice(self) -> str:
        return {
            Absence.NOT_CONFIGURED: "run `mimem doctor` to see what this machine can reach",
            Absence.UNREACHABLE: "the provider did not answer; this is usually temporary",
            Absence.REFUSED: "this model could not produce the shape; try a larger one",
            Absence.REJECTED: "the model's answer did not match the source; nothing was used",
            Absence.OVER_BUDGET: "raise --budget, or accept the shorter programme",
        }[self]


#: A deterministic implementation. Returns whether it produced anything, because that is what
#: ``assist`` needs to know and nothing else can tell it.
Deterministic = Callable[[], bool]


def classify(error: BaseException) -> Absence:
    """Which kind of absence this failure is.

    By exception type rather than by matching the message, so that rewording an error cannot
    silently change what the manifest reports.
    """
    from mimem.llm.client import LLMRefusedError, LLMUnavailableError, NoProviderError
    from mimem.llm.cost import BudgetExceededError

    if isinstance(error, BudgetExceededError):
        return Absence.OVER_BUDGET
    if isinstance(error, NoProviderError):
        return Absence.NOT_CONFIGURED
    if isinstance(error, LLMRefusedError):
        return Absence.REFUSED
    if isinstance(error, LLMUnavailableError):
        return Absence.UNREACHABLE
    return Absence.UNREACHABLE
