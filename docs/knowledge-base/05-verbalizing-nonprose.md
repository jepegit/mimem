# 05 — Verbalizing what was never meant to be spoken

Numbers, equations, tables, figures and citations are *visual random-access objects*. On the page
you glance at a table and take what you need. Read linearly at 155 words per minute, the same table
is 90 seconds of noise. There is a mature body of practice here — the accessibility community has
been solving exactly this problem for decades — and we should borrow from it rather than invent.

The governing principle throughout: **fidelity to the source is not the goal; fidelity to the
listener's resulting mental model is.** A faithful reading that produces no model is a failure.

---

## 5.1 Numbers — **[C], engineering convention**

Two separate problems, often conflated:

**(a) Normalization** — turning a token into speakable words. This is the classic TTS
*text normalization* problem (Sproat and colleagues): `14:30`, `NASA`, `1e-3`, `Fig. 4b`, `10 mA/g`
each need a verbalization, and getting it wrong is the most audible defect a system can have.
Industrial systems still lean on hand-written grammars because neural models make rare but
catastrophic errors (reading a *wrong* number is far worse than reading an awkward one). Modern
neural TTS engines do *some* of this internally and unpredictably, which is an argument for
normalizing explicitly upstream and handing the engine plain words.

**(b) Reduction** — deciding how much numeric precision survives at all. This one is ours, not the
TTS literature's, and it follows from §2.3: exact detail is precisely what listening is worst at.
Reading "zero point eight one three seven volts" aloud transmits nothing that "about eight tenths of
a volt" doesn't, and it costs several times the working memory.

Working policy:

| Case | Spoken treatment |
|---|---|
| Measurement in running prose | Round to 2 significant figures, keep magnitude, expand unit: `3.14159 mA` to "about three point one milliamps" |
| Value the argument turns on | Keep precision, and *say* that it is exact: "exactly 4.20 volts, and that number matters" |
| Large numbers | Magnitude words: `1.4e6` to "about one and a half million" |
| Percentages and changes | Prefer the comparison to the number: "roughly a third higher" |
| p-values | Verdict, not value: `p < 0.001` to "very unlikely to be chance" (configurable; a statistician may want the number) |
| Confidence intervals | "somewhere between X and Y, most likely Z" |
| Ranges, ratios, dates, currency | Explicit expansion rules, locale-aware |
| Identifiers (DOI, accession, ISBN, page numbers) | Never spoken; suppressed from audio, retained in the written track |

Every reduction is **lossless in the written track and lossy only in the audio track** — `study.md`
keeps the exact figure, so nothing is destroyed.

## 5.2 Mathematics — **[B], borrowed from accessibility research**

There are two established speech styles for mathematics, and the difference is instructive:

- **MathSpeak** — unambiguous and structural: "start fraction a over b end fraction". Fully
  reconstructible, exhausting to listen to.
- **ClearSpeak** (ETS; Frankel et al. 2016) — natural classroom phrasing, close to how a lecturer
  actually says it, at the cost of some ambiguity.

For learning-oriented listening, ClearSpeak-style phrasing is the right default; MathSpeak-style
bracketing is the fallback for expressions that are genuinely ambiguous when spoken naturally
(nested fractions, long superscripts, matrices).

But both styles answer "how do I say this expression?", and for our purposes that is the *second*
question. The first is **"what does this expression mean?"** A listener gains far more from "the
current falls off as the square root of time — that is the diffusion signature" than from a
symbol-by-symbol reading of the Cottrell equation.

Working policy — for each equation emit:
1. a one-sentence **semantic gloss**: what it says, what each symbol is, what happens when the key
   variable grows;
2. the **spoken form** only when the structure itself matters;
3. the **full LaTeX** retained in the written track.

Display equations that are pure derivation steps are candidates for dropping from audio entirely,
with a pointer ("the derivation is in the written notes").

## 5.3 Tables — **[B], from screen-reader practice**

Screen readers *linearize*: cell by cell, repeating headers for context. That works because the
user navigates actively. Our listener cannot navigate, so linearization of anything bigger than
roughly 3x4 is useless.

Strategy selection by table shape and role:

| Shape / role | Strategy |
|---|---|
| Tiny (<= 3 cols x <= 4 rows) | Full linearization, header-qualified: "for the graphite cell, 350; for the silicon cell, 1200" |
| Comparison across conditions | **Contrast narration**: name the dimension, the winner, the size of the gap, the exception |
| Many rows, one message | **Headline + top-k**: "twelve materials were tested; three stand out ..." |
| Parameter / settings table | Usually **drop from audio**; note its existence ("the full parameter table is in the notes") |
| Results table backing a claim | Narrate only the cells the surrounding text actually cites |

Rules from the accessibility guidelines that transfer directly: give the table a spoken **caption
first** so the listener can decide to disengage; always qualify a value with its header; flatten
merged and nested structures during parsing rather than trying to speak them.

## 5.4 Figures — **[B], from image-description guidelines**

The DIAGRAM Center guidelines and the SIGACCESS figure-description guidance agree on a structure we
can implement almost verbatim:

1. **Lead with a short title-like statement** (under ~125 characters).
2. **Go from general to specific.** Overview first, detail second.
3. **Do not repeat what the surrounding text already says** — describe the *new* information the
   figure adds.
4. **Give axes, labels and units** for charts; state the trend, not every point.
5. **Mention colour only when it carries meaning.**
6. **Write out abbreviations and symbols in full.**
7. **Convert dense data graphics** (pie, scatter, multi-series line) into a table or list rather
   than describing every point — and that table then goes through §5.3.
8. **Match the surrounding text's terminology and voice.**

Added for learning purposes: after the description, state **the one thing the figure is evidence
for**. A described figure that leaves no claim behind is 40 seconds of audio for nothing.

Cross-references are a special hazard: "as shown in Figure 4b" is meaningless in audio. Every figure
reference is either resolved inline (the description is placed where the reference occurs) or
rewritten ("the measurement I just described").

## 5.5 Citations, footnotes, cross-references — **[A] via the coherence principle**

Inline citations are the clearest case of extraneous processing in scientific text. A parenthetical
citation with two references spoken aloud is around four seconds of pure noise, several times per
paragraph.

Working policy, with a verbosity setting:

- **default**: suppress entirely; attribute only when the *identity* of the source is part of the
  argument ("this contradicts the earlier result from Jones's group").
- **attributed**: "a 2019 study by Smith and colleagues" — never initials, never "et al." spoken as
  letters, never a bare year in parentheses mid-sentence.
- **never spoken**: DOIs, URLs, arXiv IDs, page numbers, "ibid.", the reference list.
- **footnotes**: either promoted into the sentence (if they carry content) or dropped (if they are
  citations or asides). They must never interrupt the sentence they hang off.

## 5.6 Code, algorithms, chemical formulae, symbols — **[C]**

- **Code blocks**: narrate intent and shape ("a loop over each cycle that accumulates the discharge
  capacity"), never syntax, never punctuation. Full code stays in the written track.
- **Chemical formulae**: use the conventional spoken name where one exists (`LiNi0.8Co0.1Mn0.1O2` to
  "N M C eight one one"), otherwise a structured expansion. Domain lexicons make this tractable.
- **Greek letters and symbols**: resolved once at pre-training time ("we will call it *tau*, the
  time constant"), then used consistently for the rest of the document.
- **Units**: always expanded (`mAh/g` to "milliamp hours per gram"), never spoken as letters.

## 5.7 The recurring meta-rule

Every non-prose object is classified into one of four actions — **speak, transform, summarize,
drop** — and the choice is a function of (a) how much of the argument depends on it and (b) how
expensive it is in seconds. That decision function is shared code, not per-type ad-hoc logic.

Rules: `NUM-*`, `MTH-*`, `TBL-*`, `FIG-*`, `CIT-*`, `SYM-*`.
