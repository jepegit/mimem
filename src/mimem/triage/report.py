"""The drop report (rule COH-05).

Over-deletion is the failure mode that loses content *silently*, and a listener has no way to
notice that a section never arrived. So every dropped block is written out with its reason,
grouped so the list can be skimmed in under a minute. Reading this is how you catch a triage
rule that has gone too far.
"""

from __future__ import annotations

from collections import defaultdict

from mimem.ir import Document, TriageAction
from mimem.triage.rules import dropped, retained


def drop_report(doc: Document, *, max_examples: int = 4) -> str:
    """A Markdown report of everything triage removed and why."""
    gone = dropped(doc)
    kept = retained(doc)
    total_words = doc.word_count or 1
    kept_words = sum(len(b.text.split()) for b in kept)

    lines = [
        f"# What was left out — {doc.source.title or doc.source.path or doc.id}",
        "",
        f"- blocks: {len(kept)} retained, {len(gone)} dropped, {len(doc.blocks)} total",
        f"- words: {kept_words} of {total_words} retained ({100 * kept_words // total_words}%)",
        "",
        "Rule COH-05: nothing disappears without a trace. If something here should have been",
        "kept, the reason names the rule that removed it.",
        "",
    ]

    by_reason: dict[tuple[str, str], list[str]] = defaultdict(list)
    for block in gone:
        assert block.triage is not None
        by_reason[(block.triage.rule, block.triage.reason)].append(block.text)

    for (rule, reason), texts in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
        words = sum(len(t.split()) for t in texts)
        lines.append(f"## {reason} — {len(texts)} block(s), {words} words  <sub>{rule}</sub>")
        lines.append("")
        for text in texts[:max_examples]:
            snippet = " ".join(text.split())[:160]
            lines.append(f"- {snippet}")
        if len(texts) > max_examples:
            lines.append(f"- … and {len(texts) - max_examples} more")
        lines.append("")

    compressed = [b for b in doc.blocks if b.triage and b.triage.action is TriageAction.COMPRESS]
    if compressed:
        lines += [
            f"## Marked for compression — {len(compressed)} block(s)",
            "",
            "Retained, but shortened before narration (rule COH-02).",
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"
