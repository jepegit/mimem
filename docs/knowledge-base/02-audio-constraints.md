# 02 — What the ear can and cannot do

This is the section that most directly shapes the *sentence-level* style of the output.

---

## 2.1 The transient information effect — **[A] Robust**, and the central constraint

Written text is permanent; spoken text is transient. Sweller and colleagues showed that the
classic **modality effect** (audio + picture beats text + picture) *reverses* once the spoken
segment gets long: with longer presentations, audio narration became **worse** than written text,
because the listener must hold everything in working memory with no ability to re-inspect it
(Leahy & Sweller 2011; Singh, Marcus & Ayres 2012; Wong et al. 2012).

The recommended remedy in that literature is explicit and simple: **present spoken information in
small chunks**, or don't present it in speech at all.

Singh et al. showed directly that *segmenting* spoken text removes the disadvantage — the transient
information effect is a function of segment length, not of speech per se.

**Implications.**
- A hard cap on the amount of new information per uninterrupted speech run (target ≈ 45–90 seconds
  of narration per segment, with an explicit boundary marker and a beat of silence).
- Long, subordinate-clause-heavy academic sentences must be split. A sentence a reader parses by
  re-scanning it twice is simply lost in audio.
- Anything that would require the listener to "look back" must be replaced by explicit restatement.
→ Rules `SEG-*`, `SENT-*`.

## 2.2 Working memory capacity

Working memory holds only a handful of novel elements at once (~4 chunks for novel material), and
*element interactivity* — how many pieces must be held simultaneously to understand something — is
what actually determines load. A definition with three interacting parts is not three facts; it is
one high-interactivity item that must be built up piece by piece.

**Implications.** Never introduce more than ~2–3 genuinely new terms inside one segment; if the
source does, split the segment and add a scaffold. Build multi-part definitions incrementally
("first, ... ; now add to that, ...") rather than stating them whole. → Rules `LOAD-*`.

## 2.3 Listening vs. reading comprehension — **[B]**

The evidence is genuinely mixed and worth stating honestly:

- Rogowsky, Calhoun & Tallal (2016) found **no significant difference** between reading, listening,
  and both, for narrative non-fiction comprehension.
- Other work finds listening worse, particularly for **exact detail recall** (names, numbers,
  precise phrasing) and after a delay, while **gist comprehension** is roughly equivalent.
- Attention is a larger factor for listening: listeners are typically doing something else, in a
  noisier environment, and cannot notice that they have drifted.

**Implications.** Two design consequences follow.
1. The format is fundamentally fine for *gist and structure*; it is weak exactly where our source
   material is richest — precise values, names and symbols. So precise values must be **selected,
   reduced and repeated** rather than transmitted faithfully (see `05`).
2. Attention lapses are the norm, so the document must be *re-entrant*: frequent orientation cues
   ("Section 3 of 7. We are still on the calibration problem.") let a drifted listener rejoin
   without rewinding. → Rules `ORI-*`.

## 2.4 Speech rate — **[B]**

Conversational speech is ~140–180 wpm; ~180–200 wpm is often cited as comfortable for a native
listener. Comprehension holds up to roughly 270 wpm and then falls off steeply (~315 wpm).
Efficient listening rate tracks an individual's reading rate closely (Rubin et al. 2021).

**Implications.** mimem should not fight the TTS engine's rate; instead it should **budget words**.
All duration estimates use a configurable `wpm` (default 155 for technical narration, lower than
conversational because of pauses and dense content). Duration budgets drive segmentation, spacing
intervals and the elaboration budget. Difficulty is expressed as *more words and more pauses*, not
as a rate change, because rate changes mid-stream are jarring and unevenly supported by TTS APIs.
→ Rules `DUR-*`.

## 2.5 Pauses and silence

Silence is not dead time in audio learning; it is where retrieval and imagery happen. A retrieval
prompt without a pause is just a rhetorical question. Practical constraint: current commercial TTS
engines vary in SSML support — ElevenLabs and similar neural engines honour break tags but ignore
most other SSML — so the *only* prosodic control we should rely on is **explicit break markers plus
carefully chosen punctuation and sentence length**.

**Implications.** Pauses are first-class objects in our script model, with a duration, and are
rendered either as SSML breaks or as engine-specific markers. Never rely on `<prosody>`,
`<emphasis>` or `<say-as>` surviving the engine — normalize everything in text instead.
→ Rules `PAU-*`, `TTS-*`.
