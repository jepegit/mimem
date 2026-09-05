---
icon: lucide/wrench
---

# Architecture

Nine stages, each a file-to-file transform. You can stop after any of them, edit the intermediate
JSON by hand, and resume — which matters because taste is involved and you will want to
intervene.

``` mermaid
graph TD
  A[PDF / EPUB / Markdown] --> B[1. ingest]
  B --> C[2. clean]
  C --> D[3. triage]
  D --> E[4. concepts]
  E --> F[5. verbalize]
  F --> G[6. elaborate<br/><i>the only model call</i>]
  G --> H[7. plan]
  H --> I[8. render]
  I --> J[9. lint]
  J --> K[audio.md · study.md<br/>cards.json · manifest.json]
```

## The one decision that shapes everything

**Stages 1 to 5 and 7 to 9 contain no model call at all.** Numbers, names, structure, timing,
spacing and retrieval placement are code, because they are the parts that can be tested. The
model is confined to stage 6, and to the four things that are genuinely writing problems:
explaining a term, finding a concrete image, saying why a claim follows, drawing an analogy.

The further the model is from the numbers, the fewer ways there are for it to quietly corrupt
them. And what it does write is checked: every number in a generated sentence must appear in the
sentences it was written from.

This is also why the project is usable with no API key at all. `--local` runs everything except
stage 6 and reports what each task degraded to.

## Ground rules

These hold across the codebase and are worth knowing before reading it.

**Every artefact is re-derivable, and every ID is a content hash.** No counters, no UUIDs. The
same input produces the same block IDs and the same beat IDs, so caches hit, diffs are readable,
and `mimem explain` can point at a beat from last week's run.

**Nothing vanishes silently.** Every dropped block is in the drop report with the rule that
authorised it. Every beat the duration budget cut is in `manifest.json` and in `study.md`'s
appendix. Over-deletion is the failure mode that loses content invisibly, and this is the
defence against it.

**A missing check never looks like a passed check.** Concreteness scores say whether they came
from measured norms or a morphological guess. Groundedness verdicts are `None` when unverified,
never `True`. This rule has teeth: it is why several things in the codebase are more verbose than
they would otherwise be.

**Code names the rule it implements.** A comment reading `# SEG-01` points at a paragraph of
[the design rules](../DESIGN-RULES.md), which points at a finding in
[the knowledge base](../knowledge-base/README.md). Grep for a rule ID to find everything that
touches it.

**The linter is the acceptance test.** Ninety-odd rules, a third of them mechanically checked
today, each with a passing and a failing fixture. `mimem build` exits non-zero on any error, so a
bad script cannot be emitted quietly.

## Layout

```
src/mimem/
  ir/          Block, Span, Concept, Beat, Script — the data model, pydantic throughout
  ingest/      one adapter per format; nothing downstream knows the source format
  clean/       dehyphenation, page furniture, reading order, sentences, sections
  triage/      keep / compress / transform / drop, with a reason for every decision
  concepts/    extraction, difficulty and importance scoring, the editable registry
  verbalize/   numbers, units, citations, symbols — everything that must not be a model
  llm/         transports, task prompts, schemas, cache, cost control
  verify/      the grounding gate: numbers, years, names, directions
  elaborate/   stage 6 orchestration and its degradation paths
  plan/        beats, segmentation, the spacing scheduler, the duration budget
  render/      audio.md, study.md, cards.json, manifest.json
  lint/        text rules and script rules, the acceptance test
```

## Where the interesting problems are

If you are looking for something to work on, these are the parts with real depth rather than
plumbing:

<div class="mimem-cards" markdown>

<div markdown>
### :lucide-calendar-clock: The spacing scheduler
`plan/spacing.py`. Place *n* exposures of *k* concepts on a fixed timeline so intervals are
increasing, roughly geometric, never under three minutes, and near each concept's own material.
Greedy with a repair pass, and property-tested with hypothesis.
</div>

<div markdown>
### :lucide-scan-text: Reading order
`ingest/pdf.py`. Two-column PDFs, headings that straddle the gutter, manuscripts with line
numbers welded into words. Every fix here came from a real paper breaking.
</div>

<div markdown>
### :lucide-hash: Verbalization
`verbalize/`. "0.05 and 1.50 V" has to become speech without losing the "and" or the "1". Units,
ranges, scientific notation, statistics, model designations, Greek.
</div>

<div markdown>
### :lucide-shield-check: The grounding gate
`verify/grounding.py`. The direction check is the interesting one: a claim that reverses the
paper's sign reads perfectly and is the only failure you cannot catch by ear.
</div>

</div>

## Next

[What each stage does](stages.md){ .md-button .md-button--primary } &nbsp;
[Adding to it](extending.md){ .md-button } &nbsp;
[The plan](../PLAN-part1.md){ .md-button }
