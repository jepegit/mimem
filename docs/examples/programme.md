# What a programme looks like

This is real output, produced by `mimem build tests/fixtures/docs/synthetic-paper.pdf`, from the
synthetic two-column paper the test suite generates. Nothing here was written by a model: every
sentence is either the paper's own, carrying the span it came from, or one of about a dozen named
templates. The elaboration layer that writes glosses, concrete anchors and analogies is M5.

The point of reading it is the *shape*. Compare it with what a text-to-speech engine does with the
same PDF: it starts at the running head, reads the affiliations, says "open square bracket twelve",
pronounces `0.0837` as a string of digits, tells you to see Figure 3, and never once asks you
anything.

---

## `audio.md` — what the engine says

> **This is** Interphase repair, not particle fracture, limits silicon anode life. It's by
> A. Researcher and colleagues. Here's the problem they set out from. Silicon-graphite composite
> anodes lose capacity faster than graphite alone, and the usual explanation blames fracture of the
> active particles. It'll take about eight minutes.
>
> Before we start, here are three questions to hold on to. You're not meant to know the answers yet.
>
> First. What did the part on the paper in brief say?
>
> *(…second, third…)*
>
> **Part one of three. The paper in brief.**
>
> We show instead that the dominant loss channel is repeated repair of the solid electrolyte
> interphase after volume-driven cracking. Cells cycled five hundred times at zero point five C
> retained eighty two point one plus or minus one point four percent of their initial capacity,
> corresponding to a mean loss of zero point zero eight, three seven percent per cycle, p less than
> zero point zero zero one.
>
> That was the paper in brief.
>
> What did the part on the paper in brief say? **Take a few seconds.**
>
> *(three to six seconds of silence, carried in `manifest.json`)*
>
> Here's the answer about the paper in brief. Cells cycled five hundred times at zero point five C
> retained eighty two point one plus or minus one point four percent of their initial capacity…
>
> That was one of the questions I asked at the start, the one about the paper in brief.
>
> **Part two of three. Introduction.**
>
> *(…)*
>
> There is an equation here. It is in the written notes.
>
> Discharge capacity versus cycle number for silicon-graphite, circles, and graphite, squares,
> anodes over five hundred cycles at zero point five C.
>
> *(…)*
>
> That's the paper. Now three questions across all of it, in mixed order.

Five things in that text are rules doing their job:

| What you hear | Rule |
|---|---|
| The orientation, and the length of the programme | `STR-01` |
| Questions asked before the content, and closed when the answer arrives | `STR-02`, `PRQ-02` |
| "Part one of three" rather than "Section 1 of 3" | `ORI-01`, `NUM-02`, `STR-08` |
| "Take a few seconds", then actual silence | `PAU-01` |
| The review block mixing sections rather than following them | `STR-07`, `SPC-04` |

And one is a rule declining to guess: *"There is an equation here. It is in the written notes."* A
figure or an equation the deterministic verbalizers cannot speak is announced rather than skipped
or invented. Those become real descriptions in M5.

---

## `study.md` — the same material, for reading

```markdown
## Results and Discussion

*where we are:* Part three of three. Results and Discussion.

Capacity declined smoothly over 500 cycles with no abrupt step, which is the signature of
a process that repeats a little every cycle rather than a single mechanical failure.  <sub>p2</sub>

**Q.** What did the part on Results and Discussion say? Take a few seconds.

**A.** Here's the answer about Results and Discussion. Particles recovered from cycled
electrodes were largely intact…  <sub>p2</sub>
```

The written track keeps the exact numerals the audio track had to spell out (`NUM-06`), the page
each claim came from (`GRD-04`), and a label on every sentence mimem wrote rather than the paper
(`VOI-02`).

---

## `manifest.json` — how to argue with it

```json
"concepts": {
  "c_a1b2c3d4e5": {
    "canonical": "solid electrolyte interphase",
    "difficulty": 0.62, "importance": 0.88, "budget": 0.546,
    "signals": {"abstractness": 0.71, "interactivity": 0.55, "position": 1.0, "reprise": 0.9},
    "exposures": [
      {"beat_id": "t_4e4756d5592f", "at_seconds": 88.4,  "form": "statement"},
      {"beat_id": "t_9c1e0a77b210", "at_seconds": 271.0, "form": "callback"},
      {"beat_id": "t_1f77b4d0aa93", "at_seconds": 452.6, "form": "prompt"}
    ]
  }
}
```

Three exposures at increasing intervals, each one a *different* sentence of the source, because a
repeat that is the same sentence twice produces the feeling of knowing without the knowing
(`REP-01`). The scores that decided it earns three rather than two are recorded beside it, so a
ranking you disagree with is a number you can change rather than a black box you can only complain
about — put it under `overrides` in `registry.json` and it survives every future run.

When a beat puzzles you:

```bash
mimem explain out/paper --beat t_9c1e0a77b210
```

which prints the beat's type, the rules that produced it, its cost in seconds, the concept it
serves and the source sentence behind it.
