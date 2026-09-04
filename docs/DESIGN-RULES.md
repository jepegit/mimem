# mimem design rules — the specification for generated documents

This is the contract between the [knowledge base](knowledge-base/README.md) and the code. Every
rule has an ID, a source in the literature, and a note on how it is enforced:

- **lint** — mechanically checkable by `mimem.lint`; a violation fails the build.
- **prompt** — expressed as a constraint in an LLM task prompt, then spot-checked by a lint rule
  where possible.
- **planner** — a structural decision made by `mimem.plan`, verifiable against the script model.
- **config** — exposed as a profile setting; the rule fixes the *default*, not the only option.

Priority when rules conflict: **COH > LOAD > SEG > everything else > VOI.** Deleting beats
explaining; not overloading beats completeness; being conversational is the first thing to give up.

---

## 0. The output artefacts

For each source document, mimem produces:

| Artefact | Purpose |
|---|---|
| `script.json` | The canonical script model: ordered beats with metadata, IDs, source spans, durations |
| `audio.md` | Narration text only — what the TTS engine reads. No parentheses, no citations, no symbols, no markup that would be spoken |
| `study.md` | The written companion: same content plus exact numbers, equations, figures, page anchors, citations, links back to the source |
| `cards.json` | Retrieval items (prompt / answer / concept ID / difficulty) — the seed for Part 2 |
| `manifest.json` | Concept registry, exposure log, spacing schedule, duration budget, provenance and model versions |

`audio.md` and `study.md` are deliberately *not* the same text (see KB §4.6).

---

## 1. Macro structure (`STR-*`)

**STR-01** Every document opens with an **orientation block**, 60–90 s:
what this is, who wrote it, why anyone cared, what you will be able to say afterwards, and how long
it will take. *(pre-training, signaling; planner)*

**STR-02** The orientation block ends with **2–4 prequestions** drawn from the final retrieval item
pool — never generic curiosity hooks. *(KB §4.5; planner + lint: every prequestion ID must appear in
`cards.json`)*

**STR-03** A **term pre-load** follows: at most 7 terms/symbols, each one line, ordered by when they
are first needed. Terms beyond 7 are deferred to the section that needs them. *(pre-training,
working memory; planner + lint)*

**STR-04** Body is organised as **sections → segments → beats**. Sections follow the source's
argument; segments are duration-bounded (see `SEG-01`); beats are typed
(`exposition | gloss | anchor | elaboration | prompt | answer | recap | callback | transition`).
*(planner)*

**STR-05** Each section is framed as a **problem → attempt → obstacle → resolution** arc where the
source supports it (for IMRaD papers this is near-automatic). No invented narrative content.
*(KB §3.4; prompt)*

**STR-06** Each section ends with a **micro-recap** (3 sentences max) and **one retrieval prompt**
with its answer. *(planner + lint)*

**STR-07** The document ends with a **review block**: interleaved retrieval prompts across all
sections, ordered so that no two consecutive items come from the same section. *(KB §1.4; planner +
lint)*

**STR-08** Nothing in the audio track ever refers to something the listener cannot access —
no "see Figure 3", no "as shown in the table below", no "in the previous chapter" unless that
chapter is in the same audio programme. *(lint: forward/dangling-reference check)*

---

## 2. Segmentation and pacing (`SEG-*`, `DUR-*`, `PAU-*`)

**SEG-01** Target segment length **45–90 s** of estimated narration; hard maximum 120 s. A segment
that exceeds it must be split at a discourse boundary, not mid-argument. *(KB §2.1, §4.1; planner +
lint)*

**SEG-02** Each segment boundary emits an audible marker: a one-clause transition plus a pause.
*(planner)*

**SEG-03** At most **3 new terms** per segment; at most **1 high-element-interactivity item**
(a multi-part definition, a derivation, a mechanism with more than three interacting parts).
*(KB §2.2; lint against the concept registry)*

**DUR-01** All durations are estimated from word counts at a configurable rate, default
**155 wpm** for technical narration, plus explicit pause durations. *(config)*

**DUR-02** The whole document has a **duration budget** (default: 1.4x the estimated straight-read
time of the retained source content). When the plan exceeds it, the planner drops beats in this
order: analogy → second-order elaboration → optional figure descriptions → non-essential recaps.
Retrieval beats and glosses are never dropped first. *(planner)*

**DUR-03** Difficulty is expressed as **more words, more repetition and longer pauses**, never as a
speech-rate change. *(KB §2.4; planner)*

**PAU-01** Every retrieval prompt is followed by a pause of **3–6 s** (scaled to answer length) and
an explicit cue that thinking time is expected. A prompt without a pause is a lint error.
*(KB §1.1, §2.5)*

**PAU-02** Every imagery prompt is followed by a pause of **2–4 s**. *(KB §3.1; lint)*

**PAU-03** Segment boundaries carry a **1.0–1.5 s** pause; section boundaries **2 s**. *(planner)*

---

## 3. Sentence-level style (`SENT-*`, `ORI-*`, `SIG-*`, `VOI-*`)

**SENT-01** Median sentence length **≤ 20 words**; hard cap **35 words**; no sentence with more than
two subordinate clauses. Long source sentences are split, not compressed. *(KB §2.1; lint)*

**SENT-02** **No unresolved anaphora across a beat boundary.** "It", "this", "the former/latter",
"the above" must be replaced by the referent whenever the antecedent is more than one sentence back
or in a previous beat. *(lint: pronoun-distance check)*

**SENT-03** No parentheticals in the audio track. Parenthetical content is either promoted to its
own sentence or dropped. *(lint: no `(` in `audio.md` outside allowed constructs)*

**SENT-04** No text that only works visually: bullet glyphs, "cf.", "e.g." and "i.e." as letters,
"§", "~", "≈", quotation-mark scare quotes, ALL-CAPS emphasis. All are expanded or removed.
*(lint: character allowlist)*

**SENT-05** Front-load the point. Each paragraph's first sentence states the claim; support follows.
*(prompt)*

**ORI-01** Every section opens with a one-clause **position statement**: "Section 3 of 7 — the
calibration problem." *(KB §2.3; planner)*

**ORI-02** After any beat longer than ~90 s, re-anchor with a short "where we are" clause.
*(planner)*

**SIG-01** Announce structure before delivering it: "There are three reasons. Here is the first."
Enumerations must be counted out loud and closed ("that was the third reason"). *(KB §4.3; prompt +
lint on unclosed enumerations)*

**SIG-02** Mark importance explicitly for the top-ranked claims: "This next sentence is the core
result." Budget: at most 1 per section, so the marker keeps its force. *(planner)*

**VOI-01** All generated scaffolding is second person, spoken register, contractions allowed.
Source claims keep their own register and precision. *(KB §3.5; prompt)*

**VOI-02** Generated content is always **attributed as generated**: analogies, anchors and
elaborations are introduced with a marker ("here's a way to picture it", "my analogy, not theirs")
so the listener never confuses our scaffolding with the source's claims. *(prompt + lint on marker
presence)*

**VOI-03** No filler enthusiasm, no invented anecdotes, no rhetorical flourish that carries no
information. *(KB §4.4; prompt)*

---

## 4. Difficulty, elaboration and imagery (`DIF-*`, `ELB-*`, `IMG-*`, `ANA-*`)

**DIF-01** Every content unit receives a **difficulty score** and an **importance score**
(0–1 each), computed from measurable signals:

*Difficulty:* new-term density; abstractness (Brysbaert concreteness norms, inverted); mean
age-of-acquisition of content words; syntactic depth; element interactivity (count of interacting
referents in a definition); presence of math or dense numerics; distance from the document's
domain-frequency baseline.

*Importance:* position (abstract, conclusion, section-opening claim), reprise count in the source,
in-degree in the concept graph, whether a figure/table is cited in support, explicit author
signalling ("we show that", "crucially").

*(planner; both scores are recorded in `manifest.json` so they can be audited and tuned)*

**DIF-02** The **elaboration budget** for a unit is a monotonic function of `difficulty x
importance`. It is spent, in this order, on: gloss → concrete anchor → elaborative "why" →
worked micro-example → analogy → extra spaced repetition → extra retrieval item. *(planner)*

**DIF-03** For units above the element-interactivity threshold, the budget shifts to **support**
(incremental build-up, more glosses, slower introduction) rather than **difficulty** (prompts,
generation). Desirable difficulties are for consolidated material only. *(KB §1.3; planner)*

**DIF-04** Difficulty scores are **relative to a listener profile** (`novice | familiar | expert`
per domain), which shifts the new-term threshold and gloss depth. *(config)*

**ELB-01** Every retained key claim gets a **"why is this true / why does it follow"** sentence
where the source supports one. *(KB §3.2; planner)*

**ELB-02** Where the listener could plausibly produce the elaboration, convert it into a
prompt-then-answer pair instead of a statement. *(KB §1.3; planner)*

**ELB-03** No elaboration may introduce a fact absent from the source unless it is marked as
background and passes the groundedness gate (see `GRD-*`). *(lint)*

**IMG-01** Any unit with abstractness above threshold **and** importance above threshold gets a
**concrete anchor**: a short physically imaginable scene, under 40 words, followed by a pause.
*(KB §3.1; planner)*

**IMG-02** Anchors are **stable and unique**: one anchor per concept for the whole document, stored
in the concept registry, reused verbatim on every recurrence so that it becomes a retrieval cue.
Two concepts may not share an anchor. *(lint against the registry)*

**IMG-03** Anchors must be sensory and specific (objects, motion, scale, sound), not merely another
abstraction. *(prompt)*

**ANA-01** Every analogy states its **limit** in the same breath: what it gets right, where it
breaks. An analogy without a stated limit is a lint error. *(KB §3.3)*

**ANA-02** At most one analogy per concept, and analogies are the first thing cut under budget
pressure. *(planner)*

---

## 5. Repetition, retrieval and spacing (`REP-*`, `RET-*`, `SPC-*`, `PRQ-*`)

**REP-01** Repetition is **never verbatim** and **never adjacent**. Each repeat is a paraphrase at a
different level of abstraction (one-line summary → mechanism → example). *(KB §1.5; lint: n-gram
overlap between repeats of the same concept must stay below threshold)*

**REP-02** Repeat count is driven by `difficulty x importance`: default 2 exposures, up to 5 for the
hardest and most central concepts. *(planner)*

**REP-03** Whenever a repeat can be turned into a retrieval attempt, it must be. Restatement is the
fallback, not the default. *(KB §1.1; planner)*

**SPC-01** Repeats of the same concept are spaced at **increasing intervals measured in estimated
narration minutes**, with a minimum gap of 3 minutes between exposures of the same concept.
*(KB §1.2; lint on the exposure log)*

**SPC-02** Default within-document schedule: end of own segment → end of section → end of chapter →
final review. Intervals are approximately geometric (ratio ~2.5), truncated to fit the document.
*(planner; config)*

**SPC-03** The exposure log in `manifest.json` records, per concept: every exposure with its
timestamp-in-programme, its form (statement / prompt / anchor), and the resulting scheduled next
review. **Part 1 does not schedule across sessions but must emit everything Part 2 needs to.**
*(planner)*

**SPC-04** Interleaving is applied **only inside review blocks**, never to exposition. *(KB §1.4;
lint on `STR-07` ordering)*

**RET-01** Every retrieval prompt is a triple: **prompt → pause → answer**. Unanswered prompts are a
lint error. *(KB §1.1)*

**RET-02** Prompts must be **response-congruent**: if the target is a mechanism, ask for the
mechanism; if the target is a distinction, ask for the distinction. Prompt type is recorded on the
card. *(KB §1.1; planner)*

**RET-03** Prompt density: **one prompt per segment maximum**, at least one per section, plus the
review block. Over-prompting destroys flow and burns the duration budget. *(config)*

**RET-04** Answers restate enough of the question to stand alone ("the reason the capacity fades is
..."), because a listener who missed the prompt still needs the answer to make sense. *(prompt)*

**RET-05** Every prompt/answer pair is emitted to `cards.json` with its concept ID, difficulty,
source span and prompt type. *(planner)*

**PRQ-01** Prequestions are drawn from `cards.json`, 2–4 per document and 0–2 per long section.
*(KB §4.5; planner + lint)*

**PRQ-02** A prequestion is never answered immediately; the answer arrives with the content, and the
prequestion is explicitly closed ("that was the question I asked at the start"). *(planner)*

---

## 6. Triage: what gets dropped (`COH-*`)

**COH-01** Default-drop list (never narrated): running heads and footers, page numbers, author
affiliations and addresses, funding and acknowledgement sections, conflict-of-interest and ethics
boilerplate, keyword lists, reference lists, appendices unless referenced by a retained claim,
"the remainder of this paper is organised as follows", copyright notices, figure/table numbers as
labels. *(KB §4.4; deterministic rules + classifier)*

**COH-02** Default-compress list: related-work surveys (to their conclusion), methods detail not
needed to interpret results (to a one-line summary), hedging chains ("may possibly suggest" → the
claim plus one hedge), enumerated parameter settings. *(planner)*

**COH-03** No seductive details: no interesting-but-tangential asides, historical colour, or
biographical trivia, even when present in the source. *(KB §3.4; prompt + lint on generated
content)*

**COH-04** Every retained non-prose object must justify its seconds: a table/figure/equation is
retained only if a retained claim depends on it. *(planner)*

**COH-05** Drops are **recorded, not silent**: `manifest.json` lists every dropped block with its
reason, and `study.md` keeps a "what I left out" appendix. Nothing disappears without a trace.
*(planner)*

---

## 7. Non-prose verbalization (`NUM-*`, `MTH-*`, `TBL-*`, `FIG-*`, `CIT-*`, `SYM-*`)

**NUM-01** **Numeric fidelity is preserved by default** (`numeric_fidelity: exact`). Every value is
spoken at the precision the source states it, correctly verbalized. Rounding is opt-in per profile
(`rounded` = 2 significant figures in running prose) and never applies to a value a retained claim
turns on. *(KB §5.1; config — default changed from `rounded` on 2026-09-04 at the user's request:
the listener is a researcher and the numbers are the point.)*

**NUM-01a** Exactness carries a **cost in working memory**, so under `exact` the load is managed by
*framing* rather than by discarding digits: give the magnitude first and the digits second
("about four tenths of a percent per cycle — zero point three eight seven, precisely"), and repeat a
load-bearing value at the section recap rather than expecting it to survive one hearing.
*(KB §2.2, §2.3; planner)*

**NUM-01b** Long digit strings are **chunked and paced** when spoken: group after the decimal point
in pairs or triples with comma pauses, never as one undifferentiated run.
*(KB §2.1; verbalizer + lint on run length)*

**NUM-02** Numbers are normalized to words deterministically before the text reaches the TTS engine.
No raw digits, `e` notation, `%`, `±`, `×`, `/` or unit abbreviations survive into `audio.md`.
*(lint: character allowlist)*

**NUM-03** Units always expanded and always attached ("milliamp hours per gram"). *(lint)*

**NUM-04** Statistics under `exact`: p-values are spoken as stated **and** given their verdict
("p less than zero point zero zero one — very unlikely to be chance"); confidence intervals keep
both bounds; effect sizes keep the number. Under `rounded`, the verdict alone. *(config)*

**NUM-05** Identifiers (DOI, arXiv ID, ISBN, accession numbers, long hashes) are never spoken.
*(lint)*

**NUM-06** Exact values always survive in `study.md`. Reduction is audio-only. *(lint: cross-check
that every reduced value has an exact counterpart in the written track)*

**MTH-01** Every retained equation gets a **semantic gloss first**: what it says in words, what the
symbols are, what happens as the key variable changes. *(KB §5.2; planner)*

**MTH-02** Symbol-by-symbol reading only when the structure carries the meaning; use ClearSpeak-style
natural phrasing, falling back to MathSpeak-style explicit bracketing for ambiguous structures
(nested fractions, multi-term exponents, matrices). *(KB §5.2)*

**MTH-03** Pure derivation steps are dropped from audio with a pointer to the written track.
*(planner)*

**MTH-04** Full LaTeX is preserved in `study.md` for every equation, retained or dropped. *(lint)*

**TBL-01** Strategy is selected by shape and role: linearize (tiny) / contrast-narrate (comparison) /
headline-plus-top-k (many rows) / summarize-existence (parameter tables). *(KB §5.3; planner)*

**TBL-02** Spoken caption first, so the listener can disengage knowingly. *(lint)*

**TBL-03** Every spoken value is header-qualified. Merged and nested cells are flattened at parse
time. *(lint)*

**TBL-04** Hard cap: **no more than 12 spoken values from a single table**, and no more than 40 s.
Beyond that, narrate the pattern and point to the written track. *(planner)*

**FIG-01** Figure descriptions follow the accessibility template, in this order: **title-like
statement (< 125 chars) → what kind of figure → axes/labels/units → the trend or pattern → notable
exceptions → the claim it supports.** *(KB §5.4; prompt + lint on template compliance)*

**FIG-02** Do not repeat what the surrounding text already says; describe only the figure's new
information. *(prompt)*

**FIG-03** Colour is mentioned only when it carries meaning. *(prompt)*

**FIG-04** Figure descriptions are placed **where the figure is first referenced**, not where the
figure sits on the page, and the reference is rewritten so no figure number is spoken. *(planner)*

**FIG-05** Dense data graphics are converted to a table first and then handled under `TBL-*`.
*(planner)*

**FIG-06** Decorative or purely illustrative images are dropped. *(planner)*

**FIG-07** Every generated figure description is marked in `manifest.json` with the model used and a
confidence flag, because this is the highest-hallucination-risk output in the system. *(planner)*

**CIT-01** Inline citations are suppressed from audio by default. *(KB §5.5; lint)*

**CIT-02** Attribution is narrated only when the source's identity is part of the argument, and then
in spoken form ("a 2019 study by Smith and colleagues"). *(config)*

**CIT-03** Footnotes are promoted (content) or dropped (citation/aside); they never interrupt the
sentence they attach to. *(planner)*

**SYM-01** Greek letters, operators and domain symbols get a spoken form established once in the
term pre-load, then used consistently. *(planner + lint on consistency)*

**SYM-02** Acronyms are expanded on first use, then used in whichever form is more speakable, chosen
once per document. *(lint on consistency)*

**SYM-03** A per-domain **pronunciation lexicon** maps terms to spoken forms and is user-extensible.
*(config)*

---

## 8. Faithfulness (`GRD-*`)

**GRD-01** Every beat carries **source span IDs**. Beats with no span must be typed as generated
scaffolding (`anchor`, `analogy`, `orientation`, `prompt`), never as exposition. *(lint)*

**GRD-02** Exposition beats pass a **groundedness check**: each claim is verified as entailed by its
cited spans, by a separate verification pass. Failures are flagged in `manifest.json` and, above a
threshold, fail the build. *(planner)*

**GRD-03** Numbers, names, dates and directional claims ("increases with") in generated text are
checked against the source verbatim. A flipped sign or a mangled number is the worst failure this
system can produce. *(lint)*

**GRD-04** `study.md` links every section back to source page/locator, so any claim can be checked in
seconds. *(planner)*

---

## 9. TTS handoff (`TTS-*`)

**TTS-01** `audio.md` contains **only speakable characters**: letters, spaces, and a restricted
punctuation set (`. , ? ! : ; —`). Everything else is a lint error. *(lint)*

**TTS-02** Prosody is controlled through **sentence length, punctuation and explicit break markers
only**. No reliance on `<prosody>`, `<emphasis>` or `<say-as>`, which mainstream neural engines
ignore or mishandle. *(KB §2.5)*

**TTS-03** The script is emitted as **stable, content-addressed chunks** so that audio can be
re-rendered incrementally when one beat changes. *(planner)*

**TTS-04** Chunk boundaries align with beat boundaries and never split a sentence. *(lint)*

**TTS-05** An engine adapter layer converts the neutral script into engine-specific input (plain
text + break markers for ElevenLabs-class engines; SSML where supported). Engine choice must not
change the *content*. *(planner)*

---

## 10. Machine-checkable summary

The lint suite is the acceptance test for the whole system. Minimum rule set for v1:

```
STR-02  prequestions ⊆ cards            SENT-01  sentence length distribution
STR-06  section ends with recap+prompt  SENT-02  anaphora distance
STR-07  review block interleaved        SENT-03  no parentheticals in audio
STR-08  no dangling references          SENT-04  no visual-only constructs
SEG-01  segment duration bounds         TTS-01   character allowlist
SEG-03  new-term budget per segment     TTS-04   chunk/sentence alignment
PAU-01  every prompt has a pause        NUM-02   no raw numerics in audio
RET-01  every prompt has an answer      NUM-06   exact value survives in study.md
REP-01  repeats are not verbatim        MTH-04   LaTeX preserved
SPC-01  minimum spacing gap             TBL-02   caption before values
IMG-02  anchors stable and unique       FIG-01   description template compliance
ANA-01  analogy states its limit        GRD-01   beats have spans or are typed generated
COH-01  drop list respected             GRD-03   numbers/names/directions verified
```

Each lint rule ships with fixtures in `tests/fixtures/lint/` — a passing and a failing example —
so the rules stay honest as the generators change.
