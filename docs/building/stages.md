---
icon: lucide/list-ordered
---

# The nine stages

Each stage reads a file and writes a file. This page is what each one is responsible for, the
decision that shaped it, and the thing that broke on a real paper.

## 1. Ingest

**In:** a PDF, EPUB, Markdown or text file. **Out:** `doc.ir.json`.

One adapter per format, and nothing downstream knows which one ran. New formats are new adapters,
never new branches later on.

The PDF adapter is the workhorse and the one with scars. Two-column reading order is decided by
whether a block spans the gutter — and "spans" had to include *straddles*, because a two-line
title that crosses the gutter without being full width flipped whole pages into reading column
two first, silently.

## 2. Clean

**In and out:** `doc.ir.json`.

Dehyphenation across line breaks (dictionary-checked, so "co-operative" survives), running heads
and folios, paragraph fragments rejoined across column and page breaks, sentence segmentation,
section structure.

The order of operations is load-bearing and documented in `clean/pipeline.py`. Line-number
removal has to happen before dehyphenation, because a manuscript with line numbers produces
`recov-` / `19` / `ery` and joining those gives you `recov-19`. That one corrupted 241 words
before anyone noticed.

!!! note "Document-level evidence before document-level surgery"

    Three behaviours here — stripping line numbers, stripping superscript citations, handling
    maths placeholders — inspect the *whole document* before acting on any block. A single digit
    welded to a word is far more likely to be a variable than a citation; a few dozen of them is
    a house style. Deciding per block would silently corrupt papers.

## 3. Triage

**In and out:** `doc.ir.json`, plus `drop-report.md`.

Every block gets `keep`, `compress`, `transform` or `drop`, with a reason and the rule that
justified it. This is where the coherence principle is applied, and it is the largest single
effect in the literature — removing helps more than adding.

The drop report exists because over-deletion is the failure that loses content invisibly. It is
the file to skim when a programme feels thin.

## 4. Concepts

**In:** `doc.ir.json`. **Out:** `registry.json`.

What the document is *about*, and how hard each idea is. Two scores per concept:

**Difficulty** — abstractness, element interactivity, unfamiliarity, sentence density, span
length. About the listener's working memory, not the subject's prestige.

**Importance** — position, reprise count, connectedness in the co-occurrence graph, author
signalling, whether a figure supports it. About the document, not the reader.

Both are normalised *within* the document, then shifted by the listener profile. Their product is
the elaboration budget: what earns a gloss, an image, three repetitions or nothing.

!!! warning "Absolute thresholds on relative scores select nothing"

    This has bitten twice. Both scores are normalised within the document, so a threshold like
    "importance above 0.5" only ever selects the paper's own subject — which is also the least
    abstract thing in it, so "abstract *and* important" selected zero concepts on every real
    paper. Thresholds here have to be positions in the document's own distribution, or ranks.

## 5. Verbalize

**In and out:** in memory, applied during planning.

Turning written text into speakable text, deterministically, because everything that touches a
number, a name or a unit must stay in code that can be tested. The order is a pipeline and each
step depends on the last: citations first (so `[12]` is deleted rather than read as "twelve"),
then parentheses, then numbers, then symbols.

Exact by default. `0.0837 %` becomes "zero point zero eight, three seven percent" — chunked,
because a long digit run said as one stream is unhearable, but never shortened. The listener is a
researcher and the numbers are the point.

## 6. Elaborate

**In:** `registry.json`. **Out:** `registry.json`, richer.

The only stage that calls a model, and it is off by default. Four tasks, spent in the order rule
`DIF-02` gives: gloss, then concrete anchor, then the "why", then the analogy. Explaining a term
after showing its picture would be handing the listener an image of nothing.

Everything written here goes through the grounding gate before it is stored. Glosses and
why-explanations carry the spans they were written from and every number in them must appear
there. Anchors and analogies are ours — they are *supposed* to contain what the paper never said
— so they get the numeric check only, and the planner introduces them as ours.

Every task has a documented degradation path, so one unreachable figure cannot kill a
three-hundred-page book.

## 7. Plan

**In:** `doc.ir.json` + `registry.json`. **Out:** `script.json`.

Pure logic, no I/O, and the part with the real unit tests. The order of its steps is itself
load-bearing: prompts must exist before prequestions can be drawn from them, the timeline must
exist before spacing can be measured on it, and the duration budget must be enforced before the
spacing repair pass because cutting beats moves everything after them.

Sections become segments of 45–90 seconds, split at beat boundaries and at the new-term budget.
Each section closes on a recap and a question. Concepts come back at increasing intervals. The
review block interleaves.

!!! tip "The exposure log is where `SPC-01` becomes enforceable"

    "A minimum gap of three minutes between exposures" is unenforceable as written — a paper
    names its subject in most paragraphs. `plan/exposure.py` defines an exposure as a
    *deliberate* encounter, coalesces the ones a section's own structure forces together, and
    treats a close pair as an error only when the later one is a callback the scheduler chose.

## 8. Render

**In:** `script.json`. **Out:** the four artefacts.

Four views of one script, deliberately different. `audio.md` is only what gets said. `study.md`
keeps everything the audio had to leave behind, with a page number on each claim. `cards.json` is
the retrieval pool. `manifest.json` is the audit trail, one addressable chunk per beat so a
re-render only re-synthesises what changed.

Pauses live in the manifest, not in the audio text: a break marker inside `audio.md` would be
either unspeakable characters or words the engine reads aloud.

## 9. Lint

**In:** a build directory. **Out:** pass or fail.

Two halves. The text rules read `audio.md` and catch everything unspeakable — raw digits,
brackets, citations, "e.g.", dangling references to figures. The script rules read the plan and
catch everything unmemorable — a section that never asks you anything, a segment carrying five
new terms, a repeat that is the same sentence twice, an anchor two concepts share.

Every script rule ships with a passing and a failing example, as named mutations of a real plan:
"delete the answer beat", "give two concepts the same anchor". A rule with no failing example has
never been shown to work.
