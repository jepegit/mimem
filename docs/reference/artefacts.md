---
icon: lucide/files
---

# The four files

One script, four views of it, and the differences are the point. A written companion that is a
transcript of the audio would be a worse document than either.

## `audio.md`

What the speech engine says, and nothing else. One paragraph per beat.

```text
Part one of twenty one. The paper in brief.

However, the degradation of lithium-ion batteries is governed by complex nonlinear interactions
among material composition, chemistry, and operational stressors.

Here's a way to picture it. A cast-iron pan that seasons itself: the first heating burns a thin
layer onto the metal, and that burnt layer is what stops the metal rusting further.

What does gradient boosting mean? Take a few seconds.

Here's the answer about gradient boosting. The optimized models demonstrated prediction accuracy
exceeding zero point nine five with consistently low error values.
```

The rules this file has to satisfy are mechanical and checked on every build: no digits, no
brackets, no citations, no "e.g.", no reference to anything the listener cannot reach, and only
a small punctuation set — `. , ? ! : ; — ' -`.

!!! question "Where are the pauses?"

    In `manifest.json`, one `pause_after` per chunk. A break marker inside this file would be
    either unspeakable characters or words the engine reads out loud.

    Every retrieval pause is *also* spoken — "take a few seconds" — so an engine that ignores
    break markers has still told the listener to take them.

## `study.md`

The same programme for reading, with everything the audio track had to leave behind.

```markdown
## Results and Discussion

*where we are:* Part three of three. Results and Discussion.

Capacity declined smoothly over 500 cycles with no abrupt step, which is the signature of
a process that repeats a little every cycle.  <sub>p2</sub>

*here's a way to picture it:* A cast-iron pan that seasons itself…

**Q.** What did the part on Results and Discussion say? Take a few seconds.

**A.** Here's the answer… Particles recovered from cycled electrodes were largely intact…  <sub>p2</sub>
```

Three things it keeps that the audio cannot: the **exact numerals** the audio spelled out, the
**page** each claim came from, and a **label on every sentence mimem wrote** rather than the
paper. It also carries a "cut to fit the duration budget" appendix, so even the scaffolding that
was removed leaves a trace, and an equations appendix for the ones nobody narrated (rule
`MTH-04`).

And, from a PDF, **the figures themselves**. The audio track can only ever say a figure exists;
telling a reader the same thing and then sending them back to the source to look at it is the
written companion failing at the one job the spoken one cannot do. Each figure is cropped out of
the page into `figures/figure-3.png` and linked under its caption.

## `cards.json`

The retrieval pool, and the seed for reviewing later.

```json
{
  "cards": [
    {
      "id": "k_9c1e0a77b210",
      "concept_id": "c_a1b2c3d4e5",
      "subject": "solid electrolyte interphase",
      "prompt": "What does solid electrolyte interphase mean?",
      "answer": "Here's the answer about solid electrolyte interphase. …",
      "prompt_type": "definition",
      "difficulty": 0.62,
      "section_id": "b_85427b952b31",
      "spans": [{ "block_id": "b_1f77b4d0aa93", "char_start": 0, "char_end": 118, "page": 4 }]
    }
  ]
}
```

`prompt_type` is `definition`, `mechanism`, `distinction`, `value` or `recall`, and it is how the
response-congruence rule stays checkable: if the target is a mechanism, the question asks for a
mechanism. `spans` is where the answer came from, so any card can be verified against the paper
in seconds.

A card without a `concept_id` is a *topic card* — a question about a section the extractor found
no concept in. Weaker, but better than a section that never asks you anything.

## `manifest.json`

The audit trail. This is the file to open when you disagree with something.

```json
"concepts": {
  "c_a1b2c3d4e5": {
    "canonical": "solid electrolyte interphase",
    "difficulty": 0.62, "importance": 0.88, "budget": 0.546,
    "signals": { "abstractness": 0.71, "interactivity": 0.55, "position": 1.0, "reprise": 0.9 },
    "exposures": [
      { "beat_id": "t_4e4756d5592f", "at_seconds": 88.4,  "form": "statement" },
      { "beat_id": "t_9c1e0a77b210", "at_seconds": 271.0, "form": "callback" },
      { "beat_id": "t_1f77b4d0aa93", "at_seconds": 452.6, "form": "prompt" }
    ]
  }
}
```

| Section | What it holds |
|---|---|
| `duration` | Estimated length, the budget, and whether it fit |
| `structure` | Sections, segments, beats, cards |
| `concepts` | Every concept with its scores, **the signals that produced them**, and its exposure log |
| `schedule` | Per concept: how many times you met it, when the last one was, and the interval the schedule was heading towards when the document ran out — the hand-off to part two |
| `figures` | Every figure crop: its page, the rectangle it claims, the caption's subject, and where the prose refers to it |
| `dropped` | Every beat the duration budget removed, with the rule that authorised it |
| `notes` | What the planner could not do, in plain language |
| `chunks` | One per beat: id, start time, duration, pause after, content hash |

Two things are worth knowing about it.

**The signals are there so a ranking can be argued with.** A concept ranked too high is a number
you can look at, not a black box. Put a correction under `overrides` in `registry.json` and it
survives every future run.

**A crop is a claim about a rectangle.** `figures` records the page and the region each PNG was cut from, so a crop that grabbed the wrong part of the page is something you can check rather than something you have to notice.

**The chunks are content-addressed.** Re-render after editing one paragraph and only the beats
whose text actually changed have new hashes, so a future synthesis step re-renders only those.
