# Implementation plan — Part 1: source document → memorable, speakable script

**Goal.** A Python tool that takes a book chapter or a scientific paper and produces a set of
artefacts (`audio.md`, `study.md`, `script.json`, `cards.json`, `manifest.json`) that comply with
[`DESIGN-RULES.md`](DESIGN-RULES.md), where `audio.md` is ready to hand to a TTS engine unchanged.

**Non-goals for Part 1.** No TTS synthesis, no audio player, no cross-session scheduling, no GUI, no
multi-user anything. Part 1 must, however, *emit the data* those need — that constraint shapes the
data model and is called out in §12.

---

## 1. Product surface

```bash
# the main path
mimem build paper.pdf --profile study --out ./out/paper

# inspect the intermediate stages (each is cached and re-runnable)
mimem ingest paper.pdf                  # -> doc.ir.json
mimem triage  doc.ir.json               # -> doc.triaged.json  (+ a human-readable drop report)
mimem concepts doc.triaged.json         # -> registry.json     (edit this by hand if you like)
mimem plan    doc.triaged.json          # -> script.json
mimem render  script.json               # -> audio.md, study.md, cards.json
mimem lint    ./out/paper               # -> pass/fail + violation report
mimem explain ./out/paper --beat b0142  # why does this beat exist? which rule, which source span?
```

Two design commitments visible in that CLI:

1. **Every stage is a file-to-file transform.** You can stop after `concepts`, hand-edit
   `registry.json` (fix a bad anchor, add a term you already know so it gets no gloss), and resume.
   This matters because taste is involved and you will want to intervene.
2. **`mimem explain` exists from day one.** Every beat traces back to a rule ID and a source span.
   Without it, tuning the system becomes guesswork.

### Profiles

`profiles/*.yaml` set the knobs. Ship three:

| Profile | Duration multiplier | Prompts | Repetitions | Use |
|---|---|---|---|---|
| `skim` | 0.5x | 1 per section | 1 exposure | Deciding whether to read the paper properly |
| `study` | 1.4x | 1 per segment | 2–3 exposures | The default |
| `drill` | 2.2x | 2 per segment | 3–5 exposures, review block doubled | Material you must actually own |

Plus `listener.yaml`: your domain expertise levels (`electrochemistry: expert`,
`machine-learning: familiar`), a personal known-terms list, and a pronunciation lexicon. The
expertise setting is what stops the system from explaining "electrolyte" to you for the hundredth
time — and it is the single biggest quality lever for a domain specialist.

---

## 2. Architecture

```
                 ┌──────────────┐
  PDF/EPUB/ ───► │ 1. ingest    │──► Document IR (blocks, spans, page anchors, assets)
  DOCX/HTML/TeX  └──────────────┘
                        │
                 ┌──────▼───────┐
                 │ 2. clean     │  dehyphenate, reading order, sentence split, footnote reattach
                 └──────┬───────┘
                 ┌──────▼───────┐
                 │ 3. triage    │  keep / compress / transform / drop   (COH-*)
                 └──────┬───────┘
                 ┌──────▼───────┐
                 │ 4. concepts  │  terms, symbols, definitions, difficulty + importance scores
                 └──────┬───────┘
                 ┌──────▼───────┐
                 │ 5. verbalize │  numbers, math, tables, figures, citations  (NUM/MTH/TBL/FIG/CIT)
                 └──────┬───────┘
                 ┌──────▼───────┐
                 │ 6. elaborate │  glosses, anchors, analogies, why-explanations, cards  (LLM)
                 └──────┬───────┘
                 ┌──────▼───────┐
                 │ 7. plan      │  beats, segments, spacing schedule, budget  (SEG/SPC/RET/STR)
                 └──────┬───────┘
                 ┌──────▼───────┐
                 │ 8. render    │  audio.md / study.md / cards.json / manifest.json
                 └──────┬───────┘
                 ┌──────▼───────┐
                 │ 9. lint      │  the acceptance test — fails the build
                 └──────────────┘
```

Stages 1–5 are **deterministic-first**: rules and parsers, with LLM calls only where rules genuinely
cannot reach (figure descriptions, table strategy selection on ambiguous cases). Stage 6 is
LLM-dominant. Stages 7–9 are pure logic over data structures and are the parts with real unit tests.

That split is deliberate: the further the LLM is from the numbers, names and structure, the fewer
ways there are for it to quietly corrupt them.

---

## 3. The data model

Pydantic v2 throughout, one module (`mimem/ir/`), JSON-serialisable, versioned with a `schema_version`
field so old artefacts can be migrated rather than silently misread.

```python
class Span(BaseModel):  # a citable location in the source
    doc_id: str
    block_id: str
    char_start: int
    char_end: int
    page: int | None = None


class Block(BaseModel):
    id: str  # stable, content-derived
    kind: Literal[
        "heading",
        "para",
        "list_item",
        "figure",
        "table",
        "equation",
        "caption",
        "footnote",
        "code",
        "reference",
        "frontmatter",
    ]
    level: int | None = None  # heading depth
    text: str = ""
    role: Literal[
        "title",
        "abstract",
        "body",
        "methods",
        "results",
        "discussion",
        "refs",
        "ack",
        "boilerplate",
        "unknown",
    ] = "unknown"
    parent_id: str | None = None
    page: int | None = None
    assets: list[AssetRef] = []  # image crops, table CSV, LaTeX source
    triage: TriageDecision | None = None  # filled by stage 3


class Concept(BaseModel):
    id: str
    canonical: str  # "solid electrolyte interphase"
    aliases: list[str]  # ["SEI"]
    spoken: str  # "S E I"  (SYM-01/02)
    kind: Literal["term", "symbol", "quantity", "entity", "method", "claim"]
    short_def: str  # one line, for the term pre-load
    long_def: str | None  # for first full introduction
    anchor: Anchor | None  # IMG-01/02 — stable concrete image
    analogy: Analogy | None  # ANA-01 — must carry `limit`
    difficulty: float  # 0..1  (DIF-01)
    importance: float  # 0..1  (DIF-01)
    signals: dict[str, float]  # the components, for auditing
    first_span: Span
    exposures: list[Exposure] = []  # filled by the planner (SPC-03)


class Beat(BaseModel):
    id: str
    type: Literal[
        "orientation",
        "preload",
        "exposition",
        "gloss",
        "anchor",
        "analogy",
        "elaboration",
        "prompt",
        "pause",
        "answer",
        "recap",
        "callback",
        "transition",
        "figure",
        "table",
        "equation",
        "review",
    ]
    text: str  # already verbalized, audio-ready
    written_text: str | None  # richer variant for study.md
    concept_ids: list[str] = []
    spans: list[Span] = []  # GRD-01: exposition beats must be non-empty
    rules: list[str] = []  # which DESIGN-RULES produced this beat
    est_seconds: float
    generated: bool  # True = ours, not the source's
    provenance: Provenance | None  # model, prompt hash, groundedness verdict


class Script(BaseModel):
    schema_version: int
    source: SourceMeta
    profile: str
    segments: list[Segment]  # each holds beats and a duration
    registry: dict[str, Concept]
    schedule: list[ScheduledReview]  # SPC-03, the handoff to Part 2
    dropped: list[DropRecord]  # COH-05, nothing vanishes silently
```

The `rules: list[str]` field on every beat is what makes `mimem explain` and the whole
literature-to-code traceability real rather than aspirational.

---

## 4. Stage-by-stage

### Stage 1 — ingest

| Format | Library | Notes |
|---|---|---|
| PDF (general) | **PyMuPDF** | Fast, gives blocks, spans, fonts, image rects; our workhorse |
| PDF (scholarly) | **GROBID** (optional, Docker) | Far better section/reference/figure structure for papers; use when available, fall back to PyMuPDF |
| PDF (hard layouts) | **docling** or **marker** (optional) | Two-column, tables; heavy dependencies, so optional extras |
| EPUB | **ebooklib** + **BeautifulSoup** | Books; chapter structure comes for free |
| DOCX | **python-docx** | |
| HTML | **trafilatura** or **readability-lxml** | Boilerplate removal already solved |
| LaTeX | **pylatexenc** | Best case: math and structure arrive intact |

Failure modes to handle explicitly, because they will all happen: scanned PDFs with no text layer
(detect, then either OCR via `ocrmypdf`/Tesseract or fail loudly), two-column reading order,
running heads that vary by page, ligature and hyphenation damage, and math rendered as images.

**Adapter contract:** every adapter returns `Document` + assets; nothing downstream knows the source
format. New formats are new adapters, never new branches downstream.

### Stage 2 — clean

Deterministic and heavily unit-tested: dehyphenation across line breaks (dictionary-checked so
"co-operative" survives), running-head/footer detection (repeat across pages), reading-order repair,
sentence segmentation with **pysbd** or **syntok** (they handle "Fig.", "et al.", "e.g." and decimals
— a naive `split('.')` produces garbage on scientific text), footnote reattachment, and a language
check.

### Stage 3 — triage

Three tiers, cheapest first:

1. **Rules** (`COH-01`): structural roles, regex families (DOIs, ORCIDs, running heads),
   section-title matching for acknowledgements/funding/ethics. Handles the large majority.
2. **Heuristics**: reference-density, boilerplate n-grams, block length distribution.
3. **A classifier call** only for genuinely ambiguous blocks, batched (see §5).

Output: every block tagged `keep | compress | transform | drop` with a reason string. Emits
`drop-report.md` for a human to skim — because over-deletion is the failure mode that loses content
silently, and this report is how you catch it.

### Stage 4 — concepts

- **Candidate extraction**: acronym-definition patterns ("solid electrolyte interphase (SEI)"),
  definitional sentence patterns ("X is defined as", "we call X"), noun-phrase chunking (spaCy),
  symbol harvesting from math, plus first-occurrence tracking.
- **Difficulty signals** (all computable without an LLM):
  - abstractness: mean inverted Brysbaert concreteness of content words;
  - unfamiliarity: mean age-of-acquisition; corpus-frequency delta against a general-English
    baseline (wordfreq) and against a domain baseline;
  - element interactivity: count of distinct referents that must be co-held in the definition;
  - syntactic depth; math and numeric density; new-terms-per-100-words.
- **Importance signals**: position (abstract, conclusion, section-opening), reprise count,
  concept-graph in-degree (co-occurrence graph over sentences), whether a figure or table is cited
  in support, author signalling phrases.
- Scores are normalised **within the document**, then shifted by the listener's domain expertise.
- The registry is written as human-editable JSON. **You are expected to edit it.**

### Stage 5 — verbalize

A registry of `Verbalizer` classes, each `handles(block) -> bool` and
`verbalize(block, ctx) -> list[Beat]`. Deterministic ones first:

- `NumberVerbalizer` — significant-figure reduction, unit expansion, scientific notation, ranges,
  percentages, statistics; built on **pint** for units and a hand-written number-to-words module
  (do not trust the TTS engine to do this; see KB §5.1). Every reduction records the exact original
  for `study.md` (`NUM-06`).
- `MathVerbalizer` — parse LaTeX with `pylatexenc`; produce ClearSpeak-style speech. First choice is
  to shell out to **Speech Rule Engine** (Node) when present, since it is a mature implementation of
  exactly this; fallback is our own subset covering fractions, powers, subscripts, roots, sums,
  integrals and common operators. The *semantic gloss* (`MTH-01`) is an LLM task, not a rules task.
- `CitationVerbalizer`, `SymbolVerbalizer`, `CodeVerbalizer` — rules only.
- `TableVerbalizer` — shape analysis (rows × cols × numeric density × header structure) picks the
  strategy from `TBL-01`; contrast narration and top-k selection are computed numerically, then an
  LLM writes one sentence around the selected numbers. **The LLM never sees the whole table and never
  chooses the numbers** — that keeps `GRD-03` enforceable.
- `FigureVerbalizer` — crop the figure region, pass the image plus its caption plus every in-text
  sentence that references it to a vision call, with the `FIG-01` template as a structured output
  schema. Confidence is recorded (`FIG-07`); low confidence degrades to caption-only narration
  rather than inventing.

### Stage 6 — elaborate (LLM)

Typed tasks, each with an input schema, an output schema, a prompt template, and fixtures:

| Task | Output | Notes |
|---|---|---|
| `gloss` | short + long definition, spoken form | Grounded in the definitional span |
| `anchor` | concrete scene ≤ 40 words | Must be sensory; uniqueness checked against registry |
| `analogy` | mapping + **limit** | Rejected if `limit` is empty (`ANA-01`) |
| `why` | 1–2 sentence elaboration | Must cite spans |
| `card` | prompt, answer, type, difficulty | Prompt type from `RET-02` |
| `compress` | shortened restatement | For `COH-02` blocks |
| `figure_describe` | `FIG-01` template fields | Vision |
| `equation_gloss` | semantic reading | |
| `verify` | entailment verdict + evidence | The groundedness gate (`GRD-02`) |

Implementation notes, following the `claude-api` skill:

- **Model**: `claude-opus-5` by default with adaptive thinking; `output_config.effort` tuned per task
  (`low` for compress/gloss, `high` for anchors, analogies and verification). A cheaper worker model
  is a *measured* decision, not an assumption — wire the model per task in config and compare on the
  eval set before downgrading anything.
- **Structured output** via `output_config.format` (or `client.messages.parse()`), with `strict`
  schemas. No free-text parsing anywhere.
- **Document citations**: pass the source text as a `document` block with `citations: {enabled: true}`.
  The response then carries `char_location` citations per claim, which is *exactly* the span
  provenance `GRD-01` requires — we get most of the groundedness machinery from the API rather than
  building it.
- **Prompt caching**: the source document and the style rules are the stable prefix; the per-task
  instruction is the volatile suffix. With dozens of calls per document this is the difference
  between a cheap run and an expensive one. Assert `usage.cache_read_input_tokens > 0` in the
  integration test, because silent cache invalidation is easy and invisible.
- **Batch API** (50 % cost, async) for the bulk per-block tasks — gloss, why, card, compress — since
  nothing here is latency-sensitive. Key results by `custom_id`, never by order.
- **Content-addressed cache** on `(task, prompt_hash, model, schema_version)` in a local
  `.mimem-cache/`. Re-running a build after editing one paragraph must not re-pay for the document.

**Cost sketch** (to be replaced with measurements in M6): a 9 000-word paper is ~13 k tokens; with
caching the marginal input per task is small, so expect roughly 250 k billed input + 60 k output
across all tasks → on the order of **$2–3 per paper** at Opus-5 rates, materially less with batch and
caching. A 120 000-word book is ~10–15x that per full pass, which is the number that will actually
decide the default model per task. Measure before optimising.

### Stage 7 — plan

Pure logic, no I/O, fully unit-testable. This is where the design rules live as code.

```
1. build the section tree from retained blocks
2. for each section: derive the narrative arc frame (STR-05)
3. compute per-concept elaboration budget from difficulty x importance (DIF-02)
4. lay down exposition beats; inject gloss / anchor / why beats where budget allows
5. segment by duration, splitting at discourse boundaries (SEG-01) and checking the
   new-term budget (SEG-03)
6. place retrieval beats (RET-03) and their pauses (PAU-01)
7. run the spacing scheduler: place callbacks at geometric intervals in narration-minutes,
   respecting the minimum gap (SPC-01/02); record every exposure (SPC-03)
8. build the review block with interleaved ordering (STR-07, SPC-04)
9. build the orientation block and select prequestions from the card pool (STR-01/02, PRQ-01)
10. enforce the duration budget by dropping beats in the DUR-02 priority order
11. emit the cross-session schedule seed
```

The spacing scheduler is the one genuinely interesting algorithm here: place *n* exposures of *k*
concepts on a timeline so that intervals are approximately geometric, no two exposures of the same
concept are closer than the minimum gap, and the natural position (end of own section) is preferred.
Greedy placement with a repair pass is enough; keep it in one module with property-based tests
(hypothesis) asserting the invariants, since those invariants *are* rules `SPC-01`/`SPC-02`.

### Stage 8 — render

Two renderers over the same `Script`, plus the sidecars. `audio.md` passes through a final
normalisation pass (character allowlist, `TTS-01`), and each beat becomes a content-addressed chunk
so Part 2 can re-synthesise only what changed (`TTS-03`).

### Stage 9 — lint

The acceptance test for the whole system; the rule set is listed in `DESIGN-RULES.md` §10. Each rule
is a class with `check(script) -> list[Violation]`, a severity, and a pair of fixtures. `mimem lint`
exits non-zero on any error-severity violation, so `build` can refuse to emit a bad script.

Cheap and high-value early rules: character allowlist, sentence length, prompt-without-answer,
prompt-without-pause, dangling reference, exact-value-survives-in-study, anaphora distance.

---

## 5. Cross-cutting concerns

**Determinism and reproducibility.** Every artefact records model IDs, prompt hashes, profile,
library versions and a run seed. Re-running the same input with the same config either hits the cache
or produces a diff you can inspect. Without this, tuning is impossible.

**Cost and rate control.** A `--dry-run` prints the planned LLM calls and an estimated cost before
spending anything; a hard budget cap per build aborts rather than surprising you.

**Failure isolation.** One failed figure description must not kill a 300-page book. Every LLM-backed
beat has a documented degradation path (figure → caption-only; anchor → omitted; analogy → omitted;
gloss → source definition verbatim), recorded in the manifest.

**Privacy.** Copyrighted books and unpublished manuscripts go through a third-party API. Make the
default explicit in config, support a `--local` mode that skips LLM stages (deterministic
verbalization plus structure only — still a real improvement over raw TTS), and never log document
content to telemetry. Worth deciding consciously before the first book goes through.

---

## 6. Repository layout

```
pyproject.toml            # uv / hatchling; optional extras: [pdf-heavy], [ocr], [grobid]
profiles/{skim,study,drill}.yaml
listener.example.yaml
src/mimem/
  cli.py                  # typer
  config.py               # pydantic-settings; profile + listener merge
  ir/                     # Block, Span, Concept, Beat, Script, Provenance
  ingest/                 # pdf.py epub.py docx.py html.py tex.py base.py
  clean/                  # dehyphenate.py order.py sentences.py footnotes.py
  triage/                 # rules.py heuristics.py classify.py report.py
  concepts/               # extract.py scoring.py registry.py norms.py
  verbalize/              # numbers.py math.py tables.py figures.py citations.py symbols.py code.py
  llm/                    # client.py tasks/ schemas.py cache.py batch.py verify.py
  plan/                   # planner.py budget.py spacing.py beats.py review.py
  render/                 # audio.py study.py cards.py manifest.py ssml.py
  lint/                   # rules/*.py runner.py
  eval/                   # metrics.py recall_test.py report.py
tests/
  unit/                   # per-module
  fixtures/lint/          # pass + fail example per lint rule
  fixtures/docs/          # small real PDFs/EPUBs, committed
  golden/                 # end-to-end expected outputs (diff-reviewed, not auto-updated)
docs/                     # knowledge base, design rules, this plan, examples
```

**Tooling**: Python 3.12, `uv`, `ruff`, `mypy --strict` on `ir/`, `plan/` and `lint/` (the parts
where types actually prevent bugs), `pytest` + `hypothesis`, `pre-commit`.

---

## 7. Milestones

Each milestone ends with something you can *listen to* or *run*, not just code.

**M0 — skeleton — ✅ done (2026-09-04).** Repo, packaging (`uv` + hatchling), CLI (`typer`), IR
models (pydantic v2), config/profiles/listener, ruff + mypy strict + pytest, GitHub Actions CI.
*Done when:* `mimem --help` works and the IR round-trips through JSON in tests. ✔

**M1 — ingest + clean — ✅ done (2026-09-04).** PDF (PyMuPDF), EPUB, Markdown/text adapters;
dehyphenation, page-furniture removal, paragraph re-joining, IMRaD section and role assignment,
sentence splitting. *Done when:* a two-column paper produces a clean, correctly ordered IR. ✔
88 tests; `mimem inspect` reports the outline, counts, estimated narration time and diagnostics.

*Deviations from the plan, and why:*

- **The test corpus is synthetic, not "three real documents".** Journal PDFs cannot be committed
  and downloading at test time makes the suite non-hermetic, so `tests/fixtures/make_paper_pdf.py`
  builds a paper with exactly the properties that matter — full-width front matter over a
  two-column body, running heads and folios, a paragraph broken across the column boundary, three
  kinds of hyphenated line break, a caption, a display equation, a reference list. The next real
  test is running it over papers from your own library, which is a step for M2.
- **Figure images are not extracted.** Page plus bounding box is recorded instead, which is enough
  to re-render a crop on demand in stage 5 at whatever resolution the vision call wants.
- **Reading order needed a stronger gutter test than planned.** The first implementation classified
  spanning blocks by width alone, and a two-line title that is only 60 % of the text width but sits
  across the midline defeated it — silently, producing a document that read column two before
  column one. Spanning is now "wide *or* straddling the gutter", and two-column detection requires
  a genuinely clear gutter (rightmost left edge before leftmost right edge). This is the kind of
  failure `mimem inspect` exists to make visible.
- **`Document.content_fingerprint()` was added** (not in the plan): a hash over content that
  excludes volatile metadata like ingestion time. It is what "ingestion is deterministic" means as
  a test, and it is the cache key stage 6 will need.

*Validated against three real papers* (a Springer article, a Cell Press article, and a preprint
served from a university repository). All three ingested without intervention; each exposed a
distinct defect, and all four are now regression-tested:

1. **Manuscript line numbers destroy words.** The preprint numbers every line, and PDF extraction
   puts those numbers into the text stream on their own line. A hyphenated word breaking around
   one gives `recov-` / `19` / `ery`, and dehyphenation — seeing a digit as the continuation —
   keeps the hyphen and produces `recov-19 ery`. 241 words in that paper were corrupted this way.
   `mimem.clean.line_numbers` now strips them, and must run before dehyphenation because it needs
   the line structure. After the fix, hyphen joins went from 4 to 36 and spurious "kept" hyphens
   from 241 to 18.
2. **Detecting line numbers is easy to get wrong.** The first detector accepted any long
   monotonic run of lone integers, and fired on the *published* Springer article, where
   affiliation superscripts (1–9) and journal folio numbers (7478–7499) interleave into
   something that looks monotonic. Two more tests were needed: density (line numbering marks
   roughly every line) and range coverage (it is contiguous — 31 values spread over a range of
   7499 is not line numbering).
3. **Front matter is not in the first few blocks.** The window was 15 blocks and gave up if it
   found no structural heading. A Springer front page runs to more than that before the
   Introduction, which begins on page 2 — so no front matter was labelled at all and the title
   was lost outright. The window is now the first page, front-matter labelling is
   positive-evidence-only, and anything it cannot identify stays `UNKNOWN` for triage.
4. **"Summary" is usually a conclusion.** Matching it as an abstract turned "6 Summary and
   future perspectives" into an abstract heading and relabelled every block after it. It now maps
   to `CONCLUSION` in the body and to `ABSTRACT` only in the front matter, where it is
   unambiguous.

Two smaller fixes came from the same run: author lists separated by middle dots (Springer's
house style) are now recognised, and repository cover sheets ("Downloaded from …",
"(article starts on next page)") are marked `BOILERPLATE` rather than being narrated.

**M2 — triage + deterministic verbalizers — ✅ done (2026-09-04).** Stage 3 (triage with a drop
report), the deterministic half of stage 5 (numbers, units, citations, parentheses, symbols), a
first stage 8 renderer (`audio.md` + `study.md`) and the stage 9 lint suite. Still no LLM anywhere.
*Done when:* a paper renders to narration text with no citation noise, no raw numerals and no
unspeakable characters, and `mimem lint` passes `TTS-01`/`NUM-02`/`CIT-01`. ✔

On the three real papers, lint errors went **189 / 126 / 137 → 0 / 0 / 0**.
`mimem narrate paper.ir.json -o out/` is the command; 152 tests.

*Design notes and deviations:*

- **`pint` was dropped from the plan.** A units library models dimensional algebra, which we do not
  need, and none of them know how a unit is *said*, which is the only thing we do. `verbalize/units`
  is a curated lexicon plus a prefix-and-base parser, and it returns `None` for a non-unit — which
  is how the number verbalizer tells "350 mAh" from "350 cells".
- **Number-to-words is ours rather than a library's.** What we need is not "render 1234 in English"
  but a set of *spoken* conventions — digit chunking (`NUM-01b`), unit attachment, scientific
  notation as a lecturer says it — that any library would have to be overridden to produce.
- **Ambiguous bare unit symbols are deliberately left alone.** A bare `C` is a C-rate to an
  electrochemist, coulombs to a physicist and Celsius to everyone else; reading "0.5 C" as
  "zero point five coulombs" is confidently wrong. `C`, `M`, `T`, `S`, `F`, `H`, `B` stay as
  letters when bare and resolve normally inside a compound (`µS/cm` is still microsiemens per
  centimetre). The listener lexicon (`SYM-03`) is where a domain reading gets set.
- **The lexicon is applied first**, before any other stage can claim a token — otherwise the number
  verbalizer turns `NMC811` into its own reading before the user's preference is ever consulted.
- **Two evidence-gated behaviours**, following the line-number pattern from M1: superscript citation
  stripping and math-placeholder handling both look at the whole document before acting, because a
  single digit welded to a word is far more likely to be a variable than a citation.

*A second pass took the remaining errors to zero.* Each was its own small mistake:

- **Reference lists were found by their end, not their start.** The rescue for a missing
  "References" heading looked at a fixed 25-block tail, which finds the last entries and misses the
  first: on a paper with thirty references, entries one to fifteen were narrated as prose, DOIs and
  all. It now walks backwards from the end of the document and stops at sustained non-entry content,
  tolerating the page furniture and mangled entries inside the run.
- **A trailing full stop hid a designation.** `XP0256.` was skipped because the lookahead excluded
  any following period — including the one that ends the sentence.
- **A large trailing number is a product name, not an exponent.** `V10` was resolving as "volts to
  the power ten" and so was left alone as a unit, digits and all. Unit exponents are now capped.
- **A unit with no number in front was never spoken.** Correct for `5 cm2`, wrong for a table
  fragment like `mAh cm2`, where no number is coming.
- **`et al.` had to move before superscript stripping.** "Heimes et al.24" only loses its marker
  once "et al." has become "and colleagues", because the marker guard requires a lower-case letter
  in front. It now lives in the citations module, where it belongs.
- **Plural cross-references** (`Tables S2 and S3`) and **pointers to material the listener cannot
  reach** ("supplemental information can be found online at …") are dropped.

**All three papers are lint-clean.**

*Known limitations, visible in the lint output rather than hidden:*

- **Model designations** (`Tesla 4680`, `18650`) are read as quantities unless the lexicon says
  otherwise; the digits-welded-to-letters case (`NMC811`, `R2`, `H2O`) is handled automatically.
- **Acronym expansion** and **sentence shortening** are the two remaining warning classes. Both need
  the concept registry and the rewriting stages, so they arrive with M4/M5 — which is why `SENT-01`
  and the acronym check are warnings rather than errors.

**M3 — concepts and scoring — done (2026-09-05).** Extraction, difficulty and importance
scoring, a human-editable registry. Still no LLM. *Done when:* for a paper in your own field the
top concepts look right, and the listener profile visibly changes them. Both hold: on the
teardown paper an expert reader's top concept becomes "teardown analysis" while "prismatic cell"
falls away, and on the AI review it is "artificial intelligence", "battery management system",
"data scarcity" — the paper's actual claims. `mimem concepts paper.ir.json` is the command;
173 tests.

*Design notes and deviations:*

- **The Brysbaert concreteness norms are not vendored.** They are someone else's dataset with
  their own terms, and about 4 MB. `concepts/norms.py` loads them from `data/concreteness.csv`
  or `MIMEM_CONCRETENESS_FILE` when present, and otherwise falls back to a morphological
  heuristic — English marks abstraction in its suffixes. The fallback is much blunter and
  `mimem concepts` says which source is live on every run, because a guess and a measurement
  must never be indistinguishable.
- **spaCy was not needed.** The plan called for noun-phrase chunking; in practice acronym
  definitions, definitional sentences and repeated sentence-bounded n-grams find the concepts
  without a model or its download.
- **Domain expertise needed a vocabulary.** The first version matched a domain *name* against
  concept text, which is inert: no concept in a real paper is called "electrochemistry", so
  every one fell back to the default level and declaring yourself an expert changed nothing at
  all. `listener.domain_terms` now names each domain's vocabulary, and `known_terms` also makes
  *compounds* easier — knowing "anode" makes "anode active material" less new ground.

*Four filters, each from watching real output:*

1. **Author names.** A corresponding author's surname recurs on every page. The document already
   knows who wrote it, so the filter asks it rather than guessing from capitalisation.
2. **Sentence-bounded n-grams.** A window running over a full stop invents phrases nobody wrote.
3. **Coordinated phrases and citation fragments.** "charging and discharging" is two ideas;
   "et al" is neither. An internal *preposition* is fine — "state of charge" is one term.
4. **Overlapping n-grams and trailing verbs.** "battery degradation" and "lithium-ion battery
   degradation" competed for one budget; "battery degradation was measured" is not a concept.

*Known limitations:*

- Concreteness is morphological until the norms file is present, which mostly costs precision on
  `IMG-01` anchor selection — the rule that needs it does not arrive until M5.
- A term named after one of the paper's own authors would be filtered out. Rare, and the registry
  is editable when it happens.

**M4 — planner and renderer, no LLM — done (2026-09-05).** Beats, segmentation, the spacing
scheduler, template-generated retrieval, and the four artefacts. *Done when:* the spacing and
structure lint rules pass on all fixtures and the property tests hold. Both do: 301 tests, of
which 13 are pass/fail fixture pairs for the structural rules and 8 are hypothesis properties
over the scheduler. `mimem build paper.pdf --out ./out/paper` now runs the whole deterministic
pipeline; `mimem plan`, `mimem render` and `mimem explain` expose the stages individually.

On the three real papers, all lint-clean:

| paper | programme | sections | prompts | concepts brought back |
|---|---|---|---|---|
| GBDT degradation | 84 min of a 90 min budget | 21 | 68 | 38 |
| BYD teardown | 52 min of a 60 min budget | 2 | 33 | 16 |
| AI for reuse | 113 min of a 119 min budget | 30 | 93 | 52 |

*Design notes and deviations:*

- **A pause is a field, not a beat.** The plan sketched a `pause` beat type. An empty-text beat
  needs a special case in every renderer, in the duration arithmetic and in `GRD-01`, for
  something with no text, no provenance and no concept. `Beat.pause_after` instead, and `PAU-01`
  is checked on the beat the pause belongs to.
- **Pauses live in `manifest.json`, not in `audio.md`.** A break marker in the audio track is
  either unspeakable characters (`TTS-01`) or words the engine reads out. The durations go in the
  chunk list, where the engine adapter (`TTS-05`) can render them; what the *listener* gets is the
  spoken cue — "take a few seconds" — which works even on an engine that ignores breaks.
- **Every repeat is a different sentence of the source.** A template cannot paraphrase, so an
  unavoidably verbatim repeat would be `REP-01` dressed up as a feature. Instead each exposure
  draws a sentence the listener has not heard yet, and when a concept runs out of them the
  callback is not emitted at all — a beat saying "keep this in mind" carries no claim, no span
  and no information.
- **The lint fixtures are mutations, not files.** The plan asked for a passing and a failing
  example per rule in `tests/fixtures/lint/`. They are in `tests/unit/test_script_lint.py`
  instead, as thirteen named mutations of a real plan — "delete the answer beat", "give two
  concepts the same anchor". A mutation says what the rule is *about* and cannot drift out of
  date as the script model changes.
- **Scaffolding goes through the verbalizers.** `ORI-01`'s own example — "Section 3 of 7" — is
  two lint errors as written, and the cross-reference stripper deletes "Section 3" because
  `STR-08` says so. Position statements say "Part three of seven".

*What the first real build changed, in order:*

1. The duration budget was measured on the raw source text, but the programme speaks the
   *verbalized* text: "0.05 V" is two words on the page and seven aloud. The budget was
   systematically too small, so it cut things nobody asked it to cut — including every recap
   `STR-06` requires. Recaps are no longer in the `DUR-02` drop order at all.
2. Sections were sized before the recap, the prompt and the callbacks were added to them, so
   segments shipped over the hard maximum. They are re-split at the end, never between a prompt
   and its answer.
3. A section's closing question was sometimes about a concept from two sections back, landing
   inside the minimum spacing gap. It now prefers a concept the section introduced, and when it
   must reach back, reaches for the one met longest ago.
4. `prompts_per_segment` was a dead knob. A paper whose headings the extractor barely finds
   became a forty-minute programme with four questions in it, which is most of the way back to
   the audiobook problem.

*Known limitations:*

- **Spacing versus structure, on short sections.** `STR-06` puts a question at the end of every
  section; `SPC-01` wants three minutes between exposures. A two-minute section cannot have
  both. Exposures inside one section coalesce into a single episode, and a close pair the
  *structure* rules placed is reported as a warning rather than an error — an error is reserved
  for a callback, which is a placement the scheduler chose and could have made differently.
- **Sections follow the headings ingestion found.** The teardown paper yields two, so its
  thirty-two segments sit under two position statements. That is an M1 limitation showing
  through, not a planner one.
- **`SENT-01` and the acronym warnings remain.** Long sentences are split only at semicolons;
  real splitting is a rewriting task and belongs to M5.

**M5 — LLM elaboration layer — done, with one caveat (2026-09-05).** Task framework, schemas,
prompts, content-addressed cache, cost control, degradation paths, the grounding gate, and the
planner beats that speak what stage 6 writes. *Done when:* the worked example in
[`docs/examples/sample-output.md`](examples/sample-output.md) can be produced end-to-end from its
source paragraph, and `GRD-03` catches a deliberately corrupted number in a test. Both hold —
`tests/unit/test_elaborate.py` builds the target rendering from the paragraph in section A and
rejects a gloss claiming a figure the paper never states. 355 tests.

**The caveat, stated plainly: the live API adapter has never been run.** There is no
`ANTHROPIC_API_KEY` in the environment this was built in, so `AnthropicClient` has made no
requests. It *is* type-checked against the installed SDK, which is worth something — that check
found a real bug, a `.input` read on a union of block types where only one of them has one — but
a type check is not a run. Everything around it is exercised — schemas, cache, cost, budget cap,
grounding, degradation, the beats — through `ScriptedClient` and `FixtureClient`. Validate the
adapter on one short paper before pointing it
at a book; the `--dry-run` flag will tell you what that costs first.

```bash
mimem elaborate paper.ir.json --dry-run     # 29 calls, an estimated $1.67
mimem build paper.pdf --llm --budget 3.00   # and a hard cap
```

*Design notes and deviations:*

- **Four transports, and the default refuses.** `NullClient` is `--local`: every task degrades
  along its documented path and the manifest says what was skipped. `FixtureClient` replays a
  recorded run; `ScriptedClient` answers by task name, which is what the tests use, because a
  digest-keyed fixture would break every time a prompt is reworded. `RecordingClient` writes
  fixtures from a live run. A build that starts billing because a flag was forgotten is a bad
  build, so `--llm` is explicit.
- **The prompt, the schema and the linter each enforce the same rules.** `ANA-01` is asked for in
  the prompt, required by `AnalogyOut`, and checked on the beat. Three mechanisms that fail
  differently is what lets an elaboration layer be added to a working pipeline without weakening
  it.
- **Anchors are checked differently from glosses.** A gloss and a why-explanation are claims
  *about the document*, so they carry their spans and every number in them must appear in those
  spans. An anchor is *supposed* to contain things the paper never said — that is what an image
  for an abstract idea is — so it gets the numeric check only, and rule `VOI-02` makes the
  planner introduce it as ours.
- **A missing check never looks like a passed check.** `GRD-02` entailment needs a model; with
  none configured the verdict is `None`, not `True`.
- **Figure descriptions are specified but not wired in.** `FigureOut` and the `figure` task
  exist, with the six-part `FIG-01` template as schema fields and a required confidence. What is
  missing is the vision plumbing — cropping the figure region and attaching the image — which
  needs a live client to be worth building. Until then figures narrate as the honest placeholder
  M2 gave them.

*What building it changed elsewhere:*

1. **Two absolute thresholds on relative scores selected nothing.** Anchors required abstractness
   ≥ 0.55 *and* importance ≥ 0.5, but both are normalised within the document: on a real paper
   only the paper's own subject clears the importance bar, and the paper's own subject is the
   least abstract thing in it. Zero anchors, ever. Abstractness now sits at the median and
   importance enters as rank.
2. **The duration budget needed a floor.** It is proportional to content, but a programme's
   orientation, prequestions, pre-load and review block cost the same whether the paper is a
   paragraph or a chapter — so on a short document the budget was spent entirely on scaffolding
   and then cut the analogy, the emphasis and the callbacks. Below ten minutes the budget now
   stops cutting: it exists to stop a three-hour book becoming a nine-hour programme, and it has
   no work to do there.
3. **`enforce` now records its own drops.** It mutated the script and left recording to the
   caller; one caller forgot, and the failure mode is a beat that vanishes without appearing in
   the "what I left out" appendix — precisely what `COH-05` exists to prevent.
4. **An author's surname arrived as "Kandahari9".** Affiliation markers are superscripts on the
   page and plain digits in the text layer, so the author filter had the name and did not
   recognise it — and a corresponding author was about to be sent for a gloss.

*Known limitations:*

- The live adapter is unexercised (above).
- No batch API yet. The plan calls for it for the bulk tasks at half price; the cost model
  already prices it (`--dry-run` reports both), but the submission path is not written.
- `compress` and `verify` are specified and callable, but the planner does not yet route
  `COH-02` blocks through the first or run the second as a build gate. The deterministic half of
  `GRD-03` runs on every elaboration today.

**M6 — lint suite complete + eval harness (1 week). Done.** All twenty-eight rules from §10 of the
design rules, plus the layer-1 metrics in §8 below, held against a committed baseline by
`mimem eval` on every pull request.

Four deviations, all of them things the work turned up rather than choices made in advance:

- **A third rule family.** `COH-01`, `MTH-04` and `NUM-06` are statements about the *difference*
  between two artefacts, not about either one, so they read a `Bundle` (script, document, audio,
  study) rather than a script. A caller that has only a script cannot run them, and
  `LintReport.skipped` now says which rules a report did not cover — a report that silently
  counted fewer rules and still said "clean" was the alternative, and it is worse.
- **`MTH-04` required changing the renderer, not just checking it.** "Every equation is in
  `study.md`, retained or dropped" was simply not true: equations triage dropped never reached
  the written track at all. `render_study` now takes the document and appends the ones the
  programme did not speak.
- **The corpus needed a document that exercises the design.** The only fixture was 575 words and
  produced *zero* concepts, so spacing, pre-loads and callbacks — most of what the system is —
  were unmeasured by anything CI ran. `tests/fixtures/docs/synthetic-sensor-paper.md` is written
  to have recurring terms, equations, a table, a figure and back matter. Supporting it meant
  teaching the Markdown adapter to recognise equations, tables and figures instead of flattening
  them into prose, which was itself the bug that made three rules unfalsifiable on Markdown.
- **`SENT-02` and `FIG-01` are warnings, not errors.** Both catch things the system cannot yet
  fix: the anaphora is in the paper's own quoted prose and there is no rewriting stage, and a
  compliant figure description needs a vision model. Failing a build on either would teach
  contributors to pass `--no-lint`, which is the worst outcome available.

Writing the six missing rules found four defects that everything else had passed: a
competing-interests sentence and a keyword list narrated aloud (triage patterns anchored at `^`,
defeated by the `Conflicts of Interest:` label publishers put in front), `$f_0$` reaching the
audio track as a bare digit (the `_` was dropped before the number rules ran, stranding the
index), and the missing equations above.

*Not done:* layers 2 and 3 of §8. `gloss_coverage` sits at zero on every local build, because
without stage 6 no term is ever defined — a real gap, now visible as a number.

**Fixed: paragraphs split by a page break were never rejoined.** Stage 2's merge only looked
at *adjacent* blocks, and a page break puts a running head and a folio between the two halves of
a paragraph — so they were never adjacent and never merged, which is the one case the module was
written for. The seam became a sentence boundary that was never there: 31 beats in a 143-minute
programme opened mid-clause, "voltage and temperature signals, achieving eight to thirteen
minutes advanced warning" spoken as though it were a sentence. Merging now looks past page
furniture and textless figures, and not past captions or headings. Rejoins on that paper went
9 → 32, and lower-case openings 31 → 8.

**Known, not fixed: two headings can merge into one section title.** On a 98-page review, stage
2's paragraph rejoining merged a heading with the one following it in 2 of 26 sections, giving
"2.3. Core ML Models and Training Strategies 2.3.1. Model Architectures and General Workflow".
The output is speakable and breaks no rule, so it is a quality defect rather than a failure; the
fix is in the column- and page-break heuristics, where a change risks every document that
currently works. Worth doing deliberately, with the corpus grown first.

**M7 — TTS handoff (0.5 week).** Chunked output with stable IDs, an ElevenLabs-shaped adapter and a
local-engine adapter (Piper/Kokoro) for cheap iteration, break-marker rendering. *Done when:* one
document goes from PDF to a playable audio file in one command — the bridge into Part 2.

Roughly 9 weeks of focused part-time work; M1–M4 are the load-bearing half and contain no LLM
dependency at all, which is deliberate.

---

## 8. Evaluation — how we know any of this works

Three layers, in increasing cost and increasing truth.

**Layer 1 — mechanical (every build, free).** Lint pass rate; duration prediction error; term-gloss
coverage; spacing-interval distribution vs. target; groundedness pass rate; % of source claims
retained; number-fidelity check.

**Layer 2 — LLM-judged (per release, cheap).** Feed `audio.md` alone to a fresh model and ask it to
answer the `cards.json` questions. This measures whether the *narration by itself* actually contains
what we claim it teaches — a surprisingly strong signal, and it catches "the answer was only ever in
`study.md`" bugs.

**Layer 3 — N-of-1 recall testing (the one that matters).** A `mimem quiz` command: after listening,
it asks you the cards, records your answers and the delay, and stores results in a local SQLite.
Over a few dozen documents this gives you a personal dataset relating profile settings (repetitions,
prompt density, anchor use) to your own 24-hour and 7-day recall. Two profiles can be alternated
across documents for a crude A/B.

This layer is why the exposure log and card metadata are in the data model from day one, and it is
what turns the whole project from "plausible-sounding design" into something you can actually
falsify. It also *is* Part 2's scheduler, arriving early.

---

## 9. Risks and how the design already addresses them

| Risk | Mitigation in the design |
|---|---|
| **Hallucinated content** — the worst failure, since a confidently narrated wrong number is worse than no audio at all | Deterministic verbalizers own all numbers; LLM never selects table values; document-citation provenance; `GRD-02` verification pass; `GRD-03` number/name/direction check; degradation paths that omit rather than invent |
| **PDF parsing garbage in, garbage out** | GROBID for papers; golden fixtures; explicit scanned-PDF detection; the drop report makes over-deletion visible |
| **Output is annoying to listen to** (over-prompting, condescension, repetition fatigue) | Profiles; listener expertise levels; `RET-03` prompt density cap; `SIG-02` budget on emphasis markers; the fastest fix loop is M2's LLM-free output — tune the feel before adding intelligence |
| **Cost blowup on books** | Prompt caching, batch API, per-task model config, `--dry-run` estimate, hard budget cap, content-addressed cache |
| **Over-engineering the learning theory** | Every rule is tied to a KB entry with a confidence tag; `[C]`-tagged rules are configurable defaults; Layer-3 evaluation is the arbiter, not the citation count |
| **Scope creep into Part 2** | Part 1 emits the schedule and cards but never plays, synthesises or schedules |

---

## 10. Decisions I have made as defaults (flag if you disagree)

1. **Python-only for Part 1.** No Rust/C is warranted — the runtime is dominated by API latency and
   PDF parsing, both already native. Revisit only if book-scale batch processing becomes a bottleneck.
2. **Claude via the official `anthropic` SDK**, `claude-opus-5` default, per-task model configurable.
3. **Markdown + JSON as the interchange format**, not a database. Files are inspectable, diffable and
   git-friendly; SQLite appears only for the personal recall log in §8.
4. **English first.** Norwegian and other languages need their own concreteness norms, sentence
   splitter behaviour and number verbalization; the architecture keeps these behind interfaces, but
   the first pass is English-only.
5. **No GUI in Part 1.** The CLI plus hand-editable JSON is a better tuning loop than a UI you would
   have to design before knowing what the knobs should be.

### Settled with the user, 2026-09-04

6. **Papers are the primary material.** Scientific articles, not books. Consequences: the PDF path
   is the priority and the EPUB adapter is a thin second; scholarly structure (abstract, IMRaD
   sections, figure/table captions, reference list) is a first-class part of the IR rather than a
   special case; GROBID moves up the roadmap; two-column reading order and math handling are M1/M2
   problems rather than later ones.
7. **Numeric fidelity defaults to `exact`.** `NUM-01` is inverted: values are spoken at source
   precision, and rounding is opt-in. The working-memory cost this creates is paid back through
   framing and repetition (`NUM-01a`) and digit chunking (`NUM-01b`), not through discarding digits.

---

## 11. Open questions still outstanding

1. **Listening context.** Commute, lab work, walking? A context where you cannot pause changes how
   aggressively we use retrieval pauses.
2. **Language.** English-only to start, or does Norwegian material need to work early?
3. **Local-only mode.** Is running everything through a hosted API acceptable for your sources, or
   should the `--local` path (no LLM stages, or a local model) be a first-class target rather than a
   fallback? Unpublished manuscripts under review would settle this.

---

## 12. What Part 2 inherits

Part 1 hands over, by construction:

- `cards.json` — retrieval items with concept IDs, prompt types and difficulty → the review queue.
- `manifest.json` exposure log and `schedule` → seeds a spaced-repetition scheduler (FSRS or SM-2)
  that already knows what you have been exposed to and when.
- Content-addressed chunks with stable IDs → incremental TTS synthesis and per-chunk playback.
- The recall SQLite from §8 → the training data for tuning intervals to *you* rather than to a
  population average.

The Part 2 player then becomes mostly plumbing: synthesise chunks, play segments, honour pauses,
capture quiz responses, schedule the next review. The intelligence stays in Part 1.
