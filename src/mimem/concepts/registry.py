"""Building the concept registry, and keeping your edits when it is rebuilt.

The plan says the registry is human-editable and that you are expected to edit it. That is only
true if editing survives: a registry that silently reverts the moment you re-run the pipeline is
a read-only file with extra steps.

So regeneration **merges**. Anything under a concept's ``overrides`` key is preserved and
reapplied; everything else is recomputed from the document. Adding

```json
"overrides": {"importance": 0.95, "short_def": "the crust that forms on the anode"}
```

to a concept makes those values stick, for good, without stopping the other signals from being
refreshed when the source changes.
"""

from __future__ import annotations

from mimem.concepts.extract import extract
from mimem.concepts.scoring import score
from mimem.config import Listener
from mimem.ir import DiagnosticLevel, Document
from mimem.ir.concepts import Concept, ConceptRegistry


def build(
    doc: Document,
    listener: Listener | None = None,
    previous: ConceptRegistry | None = None,
) -> ConceptRegistry:
    """Extract and score the concepts in ``doc``, preserving any hand edits in ``previous``."""
    listener = listener or Listener()
    candidates = extract(doc)
    concepts = score(doc, candidates, listener)

    registry = ConceptRegistry(doc_id=doc.id, listener=listener.name)
    for concept in concepts:
        registry.add(concept)

    if previous is not None:
        merge(registry, previous)

    doc.note(
        "concepts",
        f"{len(registry.concepts)} concepts; "
        f"top by budget: {', '.join(c.canonical for c in registry.ranked(3))}",
        stage="concepts",
        level=DiagnosticLevel.INFO,
    )
    if "concepts" not in doc.stages:
        doc.stages.append("concepts")
    return registry


def merge(fresh: ConceptRegistry, previous: ConceptRegistry) -> ConceptRegistry:
    """Carry hand edits from ``previous`` into a freshly built ``fresh``, in place.

    Concepts that only exist in the old registry are kept too: if you added one by hand because
    the extractor missed it, it should not disappear the next time the pipeline runs.
    """
    for concept_id, old in previous.concepts.items():
        if not old.overrides:
            continue
        current = fresh.concepts.get(concept_id)
        if current is None:
            kept = old.model_copy(deep=True)
            kept.apply_overrides()
            fresh.add(kept)
            continue
        current.overrides = {**old.overrides, **current.overrides}
        current.apply_overrides()
    return fresh


def preload_terms(registry: ConceptRegistry, limit: int) -> list[Concept]:
    """The terms to establish before the exposition starts (rules PRE-01, STR-03).

    Ordered by where they are first needed rather than by score, because a pre-load is a
    sequence the listener walks into the paper with -- and capped, because more than a handful
    of new labels at once is exactly the load the pre-training principle exists to avoid.
    """
    with_definitions = [
        c for c in registry.ranked() if c.short_def or c.aliases or c.kind.value == "symbol"
    ]
    chosen = with_definitions[:limit]
    return sorted(
        chosen, key=lambda c: (c.first_span.block_id if c.first_span else "", c.canonical)
    )
