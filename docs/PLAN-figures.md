# Plan: saying what a figure shows

A listener gets nothing from a figure. Today mimem admits that — "there is a figure here, it is
in the written notes" — which is honest and is the right default, but it is also the largest
remaining hole in what a programme carries. In a review paper the figures often *are* the
argument.

This is the plan for closing it. It is deliberately staged, because the first stage needs no
model at all and delivers most of the listener value, and the last stage is the highest
hallucination risk in the system.

---

## 1. The thing that reframes the design

A ninety-eight page review, run through the current pipeline:

| | |
|---|---|
| Blocks classified `FIGURE` | **155** |
| Actual figures | **11** (plus 5 tables) |
| Embedded images per figure | 1, 1, 2, 2, 2, 2, **38**, **39**, **66** |
| Median figure block area | 2 322 pt² — about 48×48 points |

A figure in a PDF is not an image. It is between one and sixty-six embedded fragments, most of
them smaller than a thumbnail, plus — for anything drawn by a plotting library — vector content
that produces **no image block at all**.

So the unit of description cannot be the image block. Sending those 155 to a vision model would
cost roughly fourteen times what the work is worth and would produce descriptions of panel
borders and journal ornaments.

**The caption is the index of real figures.** There are 16 of them in that paper, mimem already
extracts every one, and they are the paper's own words about what the figure shows. Everything
below follows from taking the caption rather than the image as the anchor.

---

## 2. What already exists

More than the milestone list suggests. This is a plan for four missing pieces, not for a
subsystem.

| Piece | State |
|---|---|
| `FigureOut` schema — the six template fields plus `confidence` | **Written.** FIG-01 compliance is a schema property, not prose to pattern-match |
| `tasks.figure(caption, references, document)` | **Written**, including "the image itself is attached by the caller when a vision-capable model is configured" |
| Figure geometry — page, bbox, xref per image | **Extracted**, with the ingest comment `# No file written: page + bbox is enough to re-render a crop on demand` |
| `CAPTION` block detection | **Works**, 16 of 16 found, with one false positive (§4) |
| `FIG-01` lint rule, template compliance | **Written** in M6, exempting the honest announcement |
| Grounding gate, confidence, cost ledger, fixture replay | **Written**, and reusable unchanged |

Missing: figure *units*, rendering, image transport, and placement.

---

## 3. Four stages

### Stage A — figure units (no model, no cost) — **done**

Group blocks into a `Figure`: a caption, the region it belongs to, and the sentences that refer
to it.

- **Pair caption to region by geometry, not by page.** Page-level pairing is useless — 154 of
  155 image blocks sit on a page that has a caption, and page 26 of the test paper carries
  Figures 8 and 9 with 38 image blocks between them. The rule that works, checked against every
  figure in the test paper: **take the blocks above the caption and stop at the first one that
  is not a figure.** On page 3 that is figures at y1=538 and 487 and then a paragraph at 112; on
  page 10, one figure at 713 and then a paragraph at 349. The region is the union, clipped to
  the caption's column.
- **A figure with no caption is decorative.** That is `FIG-06`, and it becomes a deterministic
  rule rather than a judgement: 139 of 155 blocks disappear here, for free.
- **Collect references.** The caption names itself — "Figure 3" — so the body sentences
  mentioning "Figure 3" are findable by search. These supply `tasks.figure(references=...)` and
  the placement anchor for `FIG-04`.
- **Tables are paired but never rendered.** Five of the sixteen captions are table captions, and
  the pairing feeds `TBL-01`'s strategy choice — but a table is *text*, and its caption sits
  above its content rather than below it (Table 2 in the test paper is at the very top of its
  page with nothing above it at all). Sending a table through the image path would be a picture
  of words.

**Stage A ships on its own.** The announcement stops being "there is a figure here" and becomes
"there's a figure here showing gas production composition for four samples — it's in the written
notes." That is the paper's own caption, fully grounded, no model, no risk, and it is most of
what a listener needed. Everything after this is an improvement on a thing that already works.

### Stage B — rendering (no model) — **done**

`page.get_pixmap(clip=rect)` over the union rect. PyMuPDF is already a dependency, and rendering
the *region* rather than the embedded images is what catches vector plots — page 10 of the test
paper has one image block and three vector drawings, and the drawings are the figure.

**Render at 100 dpi, cap the long edge.** Measured on a real figure region:

| dpi | pixels | PNG | vision tokens |
|---|---|---|---|
| 72 | 500×320 | 59 KB | ~210 |
| 100 | 695×445 | 103 KB | ~410 |
| 150 | 1042×668 | 176 KB | ~930 |

150 dpi costs four times what 72 does and shows a plot no better. This matters more for the
conversation path than the API one: every crop crosses the MCP transport as base64, which
inflates it by a third.

**As built:** `mimem.ingest.crops`, called from the pipeline before the artefacts are rendered,
because `study.md` links what it produces. Eleven crops from the test paper, 41–255 KB each, and
the two hardest cases come out right — Figure 9, which shares a page with Figure 8 and 38
fragments, is cropped to its own region; and Figure 3, which is vector-drawn, comes out whole
where an approach built on embedded images would have found nothing to crop.

It lives in the adapter layer rather than beside the renderer because its job is reading a PDF,
and that is what that layer is for. It never raises: a moved source file, a page the PDF does not
have, an empty region — each costs the reader a picture and leaves the programme untouched, which
is the right trade for something the audio track never mentions.

Write the crops into the artefact directory (`figures/fig-03.png`), record a hash in the
manifest, and link them from `study.md`. That last part has value with or without any
description: the written companion currently tells you a figure exists and makes you go back to
the PDF.

### Stage C — description, two paths, one schema — **done**

Both paths produce a `FigureOut` and pass through the same gate. Neither is a fallback for the
other; they are the two places mimem runs.

**The API path.** `Request` grows an image field; `AnthropicClient` sends an image block
alongside the instruction. Two details that will bite if they are missed:

- `Request.digest()` must hash the image bytes. It currently keys on task, prompt, model and
  schema — all identical across every figure in a document. Without the image in the digest the
  cache and the fixture store would serve figure 3's description for figure 7, and the output
  would look perfectly plausible. This is the single most dangerous line in the whole plan.
- The cost model must price images as volatile suffix tokens, not as cached prefix.

**As built.** `mimem.elaborate.figures` holds the task, the gate and the spoken form; the
description is stored on its caption block, because a figure belongs to a place in the document
rather than to a concept. The API path sends the crop with the instruction; the conversation path
has a tool of its own, `next_figure`, which hands over one crop at a time — a figure is answered
with a `figure_id` rather than a `concept_id`, and it returns an image, so neither half fitted
the concept-shaped `elaboration_plan`.

Two bugs found by running it rather than by reading it. `FIG-01`'s lint rule spelled its figure
kinds in the singular, so `chart` failed "four pie charts" — a compliant description of a
real figure. And it required the word "axis" of everything, which a pie chart does not have and
a micrograph does not have; it now accepts shares, slices, categories and a scale bar.

**The conversation path.** MCP tool results can carry image content — `mcp.types.ImageContent`
takes base64 `data` and a `mimeType`, and it is in the SDK version already pinned. So
`elaboration_plan` hands Claude Desktop the rendered crop and the assistant — already
vision-capable, already writing the glosses — writes the description and returns it through
`apply_elaborations`. This is the trick that made stage 6 free, applied to the one task that
would otherwise make a vision model a hard dependency.

**Verified, 2026-09-06.** A throwaway MCP server returned an image containing a random six-digit
code, with text that did not contain it. Claude Desktop's model read the code back correctly. The
number existed nowhere but in the pixels, and guessing a particular six-digit number is one
chance in nine hundred thousand, so tool-result images do reach the model.

Two things the run showed beyond the headline. The code was rendered as *small* text — a default
font on a 520-pixel canvas, barely legible in the chat thumbnail — and was still read correctly,
which says a 100 dpi figure crop is comfortably within reach. And the harness lied before the
system did: the probe wrote one code per *process* to a file, the host started the server more
than once, and the file ended up holding a different process's code than the one that answered.
It looked like a failure and was a race. A test whose ground truth can be overwritten by the thing
under test is not a test; the fix was a code per call, appended with a timestamp.

### Stage D — placement and voice

`FIG-04`: the description goes at the **first reference in the prose**, not where the figure sits
on the page, and the reference is rewritten so no figure number is spoken.

**And it needs a fallback, which the first draft of this plan did not have.** The test paper
references its figures twelve times across nine of them — Figures 8 and 9 are never mentioned in
prose at all. A rule that places a description at its first reference silently drops every
figure nobody refers to, which is 2 of 11 here. So: first reference if there is one, otherwise
the figure's own position in reading order within its section. The fallback is the worse
placement and it has to exist.

`FIG-05` (dense data graphics become a table first) and `FIG-06` (drop decorative) are planner
rules that stage A makes checkable. `FIG-07` — model and confidence recorded in the manifest —
is a `Provenance` field that already exists.

---

## 4. The gate

This is the part of the design that matters most, because a figure description is the only
output in the system that asserts things appearing in **no sentence of the source**. The
existing `check()` compares generated text against the spans it was written from; for a figure
there are no spans, and the image is not something `check()` can read.

Four layers, weakest to strongest:

1. **Numbers and directions against caption plus references.** The existing `ground()` — which,
   when it was actually run against a `FigureOut`, turned out **not to cover figure descriptions
   at all**. `_claim_text` read a field called `text`; `FigureOut` has six fields and none of
   them is `text`; so the gate checked the empty string and reported "accepted". A pie-chart
   description claiming hydrogen "climbs from 12.4 percent to 51.8 percent", both invented,
   passed cleanly. The fallback now reads every string field, so an unfamiliar schema fails
   closed.

2. **A figure description may not quote a value the paper never wrote in a sentence.** This is
   the rule the gate produced rather than one imposed on it. Running a *faithful* description
   through it — with percentages read correctly off the plot — rejects it too, and rightly:
   those numbers are in the image, and from the text's point of view they are indistinguishable
   from fabricated ones. A gate that rejects every accurate description would be unusable, so
   the answer is not to weaken the gate but to say what a description may contain: "well over
   half", not "60.27 percent". Quoting the paper's own stated values is fine and passes.

   This costs nothing a listener had. Audio cannot carry a four-decimal percentage anyway — that
   is what `NUM-01`'s chunking exists for — and the exact values are in `study.md` and on the
   crop, where a reader can check them against the picture rather than take them on trust.
   **Measured, on Figure 3 of the test paper.** A vision-capable model was given the crop alone
   and asked to describe it. The structure came back right — four pie charts, a shared legend, an
   inset for the small slices — and the substance came back inverted:

   | Claimed | Actually |
   |---|---|
   | "C₂H₄ (~23%) also substantial" in panel (a) | C₂H₄ is **0.09%**, a sliver; 23.35% is **H₂** |
   | "the inset shows H₂ at ~8%" | the inset holds only the sub-1% traces (0.01, 0.5, 4.27) |
   | "H₂ in the inset is around 5–7%" (panel b) | that inset is 0.01, 0.52, 0.62 — an order of magnitude out |
   | "CO now clearly dominates (~69%)" (panel c) | **60.27%**, stated with a tilde that reads as careful rounding |

   H₂ and C₂H₄ are swapped throughout, which inverts the chemistry: hydrogen is a major product
   and ethylene a trace, and the description says the reverse — in a paper whose argument is that
   gas composition is an early-warning fingerprint.

   Eleven of its fourteen numeric claims are rejected by the gate. The three that survive do so
   by **coincidence**: `35` matches the citation `[35]`, `10` and `5` match "10 to 60 min" and
   "5–15 min" in the referencing sentence. Which is the argument for the rule above rather than
   for the gate alone — a compliant description states none of those numbers, so all fourteen
   go.

   Two things this does not catch, and one it need not. The **legend misread is not a number
   error**: a description saying "ethylene dominates" when it is hydrogen passes every check
   here, and that is the strongest argument for layer 4 below. And the model, given the image
   alone, invented a framing — "different cycling stages or temperatures" — when the caption
   says the panels are four cathode chemistries. That one is designed out already:
   `tasks.figure()` passes the caption and the referencing sentences, and this run is evidence
   that doing so is load-bearing rather than polite.

3. **Confidence degrades to caption-only.** Already designed as `FIG-07`, already a required
   schema field. A description written from the caption alone should say so and then not be
   spoken as fact.
4. **No card may take its answer from a figure description.** This is the rule I would not ship
   without, and the run above is why it is not merely prudent. The legend misread — hydrogen and
   ethylene swapped — is invisible to every other layer here: no number is wrong, no direction is
   reversed, and the sentence is fluent. It would reach the listener. As one spoken sentence,
   attributed to a figure they can open in `study.md`, that is a cost worth the rest of the
   feature. As a card, it is that error rehearsed at expanding intervals until they believe it. A wrong description spoken once is a wrong sentence. A wrong description turned into
   a spaced-repetition card is a wrong fact rehearsed at expanding intervals — mimem using the
   largest effect in the learning literature to teach an error. The cost of the rule is a few
   cards; the cost of not having it is the worst failure the system can produce.
5. **Attribution without hedging.** The description is the *paper's* data, not our analogy, so
   `VOI-02`-style ownership marking would be wrong — it would file a correct description as a
   guess. "The figure shows…" is the right voice: it attributes the claim to the figure, which
   is where a listener can go and check it.

---

## 5. The false caption

`CAPTION_RE` matches the first line of a block, so on page 19 of the test paper it classified
this as a caption:

> Figure 6 exemplifies how transfer learning combined with Sha…

That is a sentence. It is also *exactly* what stage A wants as a **reference** for `FIG-04`, so
the fix and the feature are the same work.

The discriminator is not length — the false caption is 45 words and the real ones run from 5 to
88, one of them also 45. It is the **delimiter after the number**. A caption writes "Figure 6."
or "Figure 6:"; a sentence writes "Figure 6 exemplifies". Requiring `[.:—)]` after the numeral
separates all sixteen blocks in the test paper correctly, and it is one character class added to
a regex that already exists.

Getting this wrong permissively costs a figure described from a sentence about it; getting it
wrong strictly loses a figure entirely.

---

## 6. What could go wrong

| Risk | Mitigation |
|---|---|
| ~~The MCP host does not put tool-result images into the model's context~~ | **Verified false** — images reach the model (§3). This was the assumption stage C rested on |
| Region pairing grabs the wrong rectangle | Crops are written to disk and linked from `study.md`, so a wrong crop is visible rather than silent. A lint rule can check that every described figure's crop is non-empty and inside the page |
| A confidently wrong description | §4, and the card rule in particular |
| The cache serves one figure's description for another | The digest change in §3, and a test that two figures in one document produce two digests |
| Vector-only figures produce an empty region | Detect an empty crop and fall back to the caption-only announcement, which is today's behaviour and is never worse than today |

Cost is **not** on this list, and the first draft was wrong to put it there. Eleven figures at
~410 image tokens each, against a document prefix that is already cached, is not a bill anybody
will notice. The reason to cut 155 candidates to 11 is that a description of a journal logo is
*noise in the programme*, which is a quality argument and a much better one.

---

## 7. Out of scope

- Reading data *off* a plot to reconstruct a table. That is `FIG-05`'s ambition and it deserves
  its own evaluation before anyone trusts it.
- Equations as images. The same rendering machinery would serve, but `MTH-*` has its own rules.
- Describing figures in the listener's second language, or at multiple levels of detail.

---

## 8. Done when

- A paper with figures produces a programme in which each real figure is described at its first
  mention, in the template order, with the model and confidence in the manifest.
- `mimem eval` gains a figure column, and the corpus gains a document with a real figure in it.
- Every stage is separately useful: A and B improve the output with no model configured at all.

---

## 9. What reviewing this plan changed

The review was done against the test paper and the installed libraries rather than by rereading
the prose, which is the only kind of review that finds these. Six things changed; two of them
were the plan being wrong rather than vague.

**`FIG-04` would have silently dropped figures.** The plan said "place the description at the
first reference in the prose" and stopped there. Counting the references in the test paper found
twelve, across nine of the eleven figures: **Figures 8 and 9 are never mentioned in the text at
all.** A rule with no fallback would have described them and then had nowhere to put them. The
fallback is now stated, and it is the weaker placement, which is worth writing down as such.

**The false-caption discriminator I proposed does not work.** The plan said a caption is "a block
whose whole text is caption-shaped and which sits against graphics" — which is vague, and the
obvious sharpening of it, length, is useless: the one false caption is 45 words and the real ones
run 5 to 88 with another at exactly 45. Checking the actual strings found the real discriminator,
which is the **delimiter after the number** — "Figure 6." against "Figure 6 exemplifies" — and it
separates all sixteen correctly. It is also a one-character-class change rather than new
geometry, so the plan got simpler as well as correct.

**Cost was an argument I did not have.** The plan justified cutting 155 candidates to 11 partly
on expense. Measuring says a crop is ~410 vision tokens at 100 dpi and the document prefix is
already cached, so eleven of them cost nothing worth discussing. The real argument was always the
quality one — a description of a journal logo is noise in a programme — and leaning on a cost
claim that does not survive arithmetic would have made the whole section easier to dismiss.

**150 dpi was four times too much.** Measured: 72 dpi is 210 tokens, 150 dpi is 930, and the plot
is not more legible. On the conversation path every crop also crosses the transport as base64.

**Tables needed separating explicitly.** The plan had them "coming along" with the same pairing,
which is true for `TBL-01` and dangerous everywhere else: a table is text, its caption sits
*above* its content, and Table 2 in the test paper is at the very top of a page with nothing
above it at all. Rendering one would produce a picture of words.

**The region rule got specific enough to test.** "Clipped to the column and stopping at the
nearest text block" became "take blocks above the caption, stop at the first non-figure", which
was then checked against every figure in the paper and works on all of them.

One assumption survived the review unverified: `mcp.types.ImageContent` exists in the pinned SDK,
but whether Claude Desktop puts a tool result's image into the *model's* context — rather than
only showing it to the user — is not something the SDK can tell us.

It has since been tested, and it holds (§3). Which is the argument for having written it down as
an assumption rather than as a plan: it took twenty minutes to settle, and had it gone the other
way it would have invalidated a third of this document.
