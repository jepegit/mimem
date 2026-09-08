"""Build the same document twice, with and without a model, and say what changed.

The project's whole argument is that structure matters more than fluency. That is a claim about
what a model is worth here, and until now there was no way to check it: a paid build produced a
programme, and nobody could say what the money bought beyond "it has analogies in it now".

This runs the deterministic pipeline and the model-assisted one over one document and diffs the
result. Everything the eval harness already measures comes along for free -- gloss coverage,
grounding, values kept, duration -- plus the two questions specific to this comparison: **what
did the model add**, and **what did it cost**.

It is deliberately a whole-document comparison rather than a task-level log. A task-level log
would say "the model wrote fourteen glosses"; this says the programme is four minutes longer,
has nine more terms defined, kept the same values, and cost thirty cents. The second is the one
that answers "was that worth it".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from mimem.config import Listener, Profile
from mimem.eval.metrics import Metrics, measure
from mimem.llm.client import Client
from mimem.pipeline import build_all

#: Metrics where a larger number is better, for the arrow in the report.
HIGHER_IS_BETTER = frozenset(
    {
        "gloss_coverage",
        "concepts_spaced",
        "intervals_expanding",
        "grounded",
        "values_kept",
        "words_retained",
        "prompts_per_minute",
        "cards",
    }
)

#: Metrics not worth a row: identities, or numbers that say nothing about quality.
SKIP = frozenset({"document", "budget_minutes", "recurring_concepts"})


@dataclass(frozen=True)
class Change:
    """One metric, both ways."""

    name: str
    local: float
    with_model: float

    @property
    def delta(self) -> float:
        return self.with_model - self.local

    @property
    def moved(self) -> bool:
        return abs(self.delta) > 1e-9

    @property
    def better(self) -> bool | None:
        """``None`` when the direction carries no judgement (more beats is not better)."""
        if not self.moved or self.name not in HIGHER_IS_BETTER:
            return None
        return self.delta > 0


@dataclass
class Comparison:
    """What a model changed on one document, and what it cost."""

    document: str
    local: Metrics
    with_model: Metrics
    dollars: float = 0.0
    calls: int = 0
    added: dict[str, int] = field(default_factory=dict)
    absences: dict[str, int] = field(default_factory=dict)

    def changes(self) -> list[Change]:
        """Every metric that moved, biggest relative move first."""
        out: list[Change] = []
        for name, mine in self.local.model_dump().items():
            if name in SKIP or not isinstance(mine, int | float) or isinstance(mine, bool):
                continue
            theirs = getattr(self.with_model, name)
            change = Change(name, float(mine), float(theirs))
            if change.moved:
                out.append(change)
        return sorted(out, key=lambda c: -abs(c.delta) / (abs(c.local) or 1.0))

    @property
    def cost_per_gloss(self) -> float | None:
        """Dollars per term the model actually defined, or ``None`` if it defined none."""
        glosses = self.added.get("gloss", 0)
        return self.dollars / glosses if glosses else None

    def to_json(self) -> str:
        return (
            json.dumps(
                {
                    "document": self.document,
                    "local": self.local.model_dump(),
                    "with_model": self.with_model.model_dump(),
                    "cost": {"dollars": round(self.dollars, 4), "calls": self.calls},
                    "added": self.added,
                    "absences": self.absences,
                    "changed": {
                        c.name: {"local": c.local, "with_model": c.with_model, "delta": c.delta}
                        for c in self.changes()
                    },
                },
                indent=2,
            )
            + "\n"
        )


def compare(
    source: Path,
    out_dir: Path,
    profile: Profile,
    listener: Listener,
    client: Client,
    *,
    budget: float | None = None,
) -> Comparison:
    """Build ``source`` twice into ``out_dir``, and measure the difference.

    The deterministic build runs first and always, so that a model failure half-way through the
    second one still leaves a complete comparison target rather than nothing.
    """
    plain = build_all(source, out_dir / "local", profile, listener, client=None)
    local = measure(
        plain.doc,
        plain.script,
        plain.lint,
        plain.artefacts.study,
        profile,
        name=f"{source.name} (local)",
    )

    assisted = build_all(
        source, out_dir / "with-model", profile, listener, client=client, budget=budget
    )
    with_model = measure(
        assisted.doc,
        assisted.script,
        assisted.lint,
        assisted.artefacts.study,
        profile,
        name=f"{source.name} (model)",
    )

    report = assisted.elaboration
    return Comparison(
        document=source.name,
        local=local,
        with_model=with_model,
        dollars=report.ledger.spent if report else 0.0,
        calls=report.ledger.calls if report else 0,
        added=dict(report.succeeded) if report else {},
        absences={k.value: v for k, v in report.absences().items()} if report else {},
    )
