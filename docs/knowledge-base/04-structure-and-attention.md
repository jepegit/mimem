# 04 — Structure, attention and what to leave out

Mayer's multimedia principles were developed for narrated animations, i.e. for exactly the
"narration + limited or no visual channel" situation we are in. The subset below survives the
translation to audio-only.

---

## 4.1 Segmenting — **[A]**, median effect **≈ 0.98**

Break a lesson into learner-paced segments instead of one continuous stream. This is the same
finding as the transient information work in `02`, arrived at from the other direction, and it is
one of the largest effects in the multimedia literature.

**Implication.** Segment boundaries are structural objects in our script, with an audible marker
and a pause, sized by *estimated seconds of narration* rather than by source paragraphs. In a
future player (Part 2) they become the natural stop/resume points. → `SEG-*`.

## 4.2 Pre-training — **[A]**

Learners do better when they already know the *names and characteristics of the key concepts*
before the explanation starts. Pre-training offloads part of the essential processing so working
memory can spend itself on the mechanism.

**Implication.** Every document and every major section opens with a short **term pre-load**: the
handful of terms and symbols you must own before the section makes sense, each with a one-line
definition, delivered *before* the exposition rather than in-line. This is also where acronyms and
symbol pronunciations get established once. → `PRE-*`.

## 4.3 Signaling — **[A]**, effect **≈ 0.52**

Cues that expose the *organization* of the material improve learning. In audio there is no bold
text, no layout, no figure to point at — signaling must be entirely verbal.

**Implication.** Explicit verbal signposting is mandatory, not stylistic:
enumerate ("there are three reasons; here is the first"), announce structure before content, mark
transitions, and mark importance ("this next sentence is the core claim of the paper"). Verbal
signposts also serve the re-entry function from §2.3. → `SIG-*`.

## 4.4 Coherence — **[A]**, effect **≈ 0.97**

Removing interesting-but-extraneous material *improves* learning. This is the largest and most
counter-intuitive lever available to us: the single most effective thing mimem can do is **delete**.

Combined with the seductive-details literature (§3.4), the message is blunt: tangential-but-fun
content actively displaces main ideas in memory.

**Implication.** Aggressive triage of source material. Author affiliations, funding statements,
acknowledgements, running heads, reference lists, DOIs, "the remainder of this paper is organized
as follows", boilerplate ethics statements, and most hedging clauses are **dropped**, not narrated.
Everything retained must earn its place against the coherence principle. → `COH-*`.

## 4.5 Prequestions / pretesting — **[A] for the specific effect, with a sharp limit**

Asking questions *before* the content is presented improves learning — but the meta-analytic picture
is precise about *what* it improves: **g ≈ 0.54–0.66 for the specifically prequestioned content, and
essentially zero (g ≈ 0.04) for everything else** in the same lesson. Eye-tracking shows why:
prequestions redirect attention onto the prequestioned sentences.

**Implication.** This is a targeting instruction, not a decoration. Prequestions must be generated
*from the same item pool as the final retrieval items*, so that attention is steered onto exactly
what we intend the listener to retain. A generic hook ("ever wondered how batteries age?") buys
nothing measurable. And because attention is redirected *away* from non-prequestioned content,
the number of prequestions per section must be small and deliberate (2–4). → `PRQ-*`.

## 4.6 Redundancy — **[B]**, and why it does *not* forbid our repetition

Mayer's redundancy principle says: don't present identical on-screen text and narration
simultaneously. It is about *simultaneous duplication across channels*, not about repetition over
time. Spaced, paraphrased repetition (§1.2, §1.5) is a different mechanism and remains desirable.

**Implication.** Worth stating explicitly so that neither we nor a future contributor
"optimizes away" the repetition machinery by misapplying this principle. The written `study.md` and
the spoken `audio` track are deliberately *not* identical; they are two renderings for two uses.
