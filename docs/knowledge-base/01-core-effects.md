# 01 — Core memory effects

The four levers that actually move long-term retention, ordered by how much weight mimem puts on
them.

---

## 1.1 Retrieval practice (the testing effect) — **[A] Robust**

Trying to *produce* information from memory is a far stronger memory event than re-exposing
yourself to it. Meta-analyses report a medium effect of testing over restudy (**g ≈ 0.50**),
holding up in real classrooms (**g ≈ 0.50**) and transferring to new questions about the same
material (**d ≈ 0.40**).

Two moderators matter for us:

- **Response congruency.** The retrieval prompt should require the same kind of operation the
  final use requires. If the goal is to explain a mechanism, the prompt must ask for the
  mechanism, not for a term.
- **Elaborated retrieval / feedback.** Retrieval attempts followed by the correct answer are
  reliably better than unanswered attempts, and elaborated retrieval (retrieve *and* explain)
  outperforms bare recall. Feedback also rescues failed retrievals, which is essential in audio
  where we cannot check whether the listener answered.

**Implication for mimem.** The single highest-value thing the generated document can contain is
*question → silence → answer* structures, placed inside the narration itself. Every retrieval
beat must be followed by the answer, because a listener who fails silently gets nothing otherwise.
→ Rules `RET-*`.

---

## 1.2 Spacing and spaced retrieval — **[A] Robust**

Repetitions separated in time beat repetitions massed together. Cepeda et al.'s meta-analysis
covered 254 studies / >14 000 participants and found distributed practice superior in 259 of 271
comparisons. Combining spacing *with* retrieval (spaced retrieval practice) gives a strong benefit
over massed retrieval (**g ≈ 0.74**, Latimier et al. 2021).

Two useful details:

- **Gap size scales with the target retention interval.** The common rule of thumb is that the
  optimal inter-study gap is roughly **10–20 % of how long you want to remember it**. Want it in
  a month → review every 3–6 days.
- **Expanding vs. uniform intervals barely differ** (g ≈ 0.03) *unless* there are many repetitions,
  where expanding starts to win. So: don't over-engineer the schedule.

**Implication for mimem.** Repetition inside a single document must be *spaced*, not adjacent.
A key claim gets restated at the end of its own section, again at the end of the chapter, and
again in the closing review — at deliberately increasing distances, measured in **estimated
listening minutes**, not in paragraphs. Cross-document/cross-session spacing is Part 2, but Part 1
must already emit the per-item exposure record that Part 2 will schedule from. → Rules `SPC-*`.

---

## 1.3 Generation effect and desirable difficulties — **[B] Solid but bounded**

Information you produce yourself is remembered better than information handed to you. This sits in
the broader family of *desirable difficulties*: conditions that feel harder and slower during
study but produce better retention. The mirror image is the **fluency illusion** — smooth,
easy-feeling exposure (re-reading, listening passively to a well-produced narration) inflates
confidence without improving memory, and makes learners stop studying too early.

Important boundary condition: for **high element-interactivity material** (many interacting
components that must be held in mind at once, e.g. a derivation), added difficulty becomes
*undesirable* — it consumes the same working memory the learning needs. Also, a 2025 conceptual
replication found text-generation benefits for expository text are weaker than the classic
word-list literature suggests.

**Implication for mimem.** Insert difficulty deliberately and sparingly, and never in the middle of
a dense derivation. Prefer *generation prompts* (predict, explain, produce an example) on
consolidated material, and prefer *support* (worked-out narration, glosses, chunking) on dense
material. The generated document must therefore know how dense each passage is. → Rules `GEN-*`,
`DIF-*`.

---

## 1.4 Interleaving — **[B] Solid, but mostly *not* for us**

Brunmair & Richter's meta-analysis (59 studies, 238 effect sizes) found an overall benefit of
interleaved over blocked practice (**g = 0.42**) — but it is highly moderated by between-category
similarity. It was strongest for perceptual categories such as painters' styles (**g = 0.67**) and
**not significant for expository texts (g = 0.21)** and actually **negative for word learning
(g = −0.39)**.

**Implication for mimem.** This is a case where the literature tells us *not* to build something.
Do **not** shuffle expository content to interleave topics — our material is exactly the type where
interleaving fails. Keep exposition blocked and coherent. Interleaving is applied only inside
*review/quiz blocks*, where items from different sections are mixed, which is closer to the
condition where it works and is anyway a spacing manipulation. → Rule `SPC-04`.

---

## 1.5 What does *not* work (so we must not accidentally build it)

- **Re-reading / re-listening** as the primary strategy: low utility, high fluency illusion.
  Simply generating a "nicer" audio version of the same text and playing it twice is the failure
  mode we are trying to escape.
- **Highlighting and summarizing** were rated *low utility* by Dunlosky et al. (2013) for typical
  learners — the value is in generating the summary under retrieval conditions, not in owning one.
  An auto-generated summary that the listener passively consumes buys much less than it appears to.
- **Massed repetition** ("say it three times in a row"): near-zero long-term benefit compared to
  the same three repetitions spaced out.

**Implication.** Every repetition mimem emits must be *spaced*, *varied in form* (paraphrase, not
verbatim), and where possible *converted into a retrieval attempt* rather than a restatement.
→ Rules `REP-*`.
