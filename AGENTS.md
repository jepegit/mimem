# For AI agents

You are welcome here. This page exists because "agents are welcome" is easy to say and unhelpful
on its own — what you actually need is the shape of the project, what counts as done, and the
three or four conventions that a patch will be judged on.

Read [CONTRIBUTING.md](CONTRIBUTING.md) too. This page is the supplement, not the replacement.

Two asks before anything else:

1. **Say in the pull request that you are an agent**, and which model. Not because it will be
   judged differently, but because the person reviewing it should know what kind of question to
   ask back.
2. **Have a human who can answer for the change.** Not to rubber-stamp it — to say why it was
   made and what happens if it is wrong.

## What this project is

mimem turns a document into audio designed to be *remembered* rather than merely read aloud. Nine
stages, each a file-to-file transform:

```
ingest → clean → triage → concepts → verbalize → elaborate → plan → render → lint
```

Stage 6 is the only one that calls a model. Everything else is deterministic on purpose: numbers,
names, structure, timing and spacing are code because they are the parts that can be tested. The
further a model is from the numbers, the fewer ways there are for it to quietly corrupt them.

Start with [the architecture](https://jepegit.github.io/mimem/building/) and
[the nine stages](https://jepegit.github.io/mimem/building/stages/).

## What "done" means

```bash
uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy
```

All four, clean, on Ubuntu and Windows across Python 3.11 and 3.13. CI runs exactly this plus a
documentation build. There is no separate review gate that lets a red build through.

For anything touching the pipeline, also run it on a real document and read the output:

```bash
uv run mimem build paper.pdf --out out/check && uv run mimem lint out/check
```

Zero errors. Warnings are expected — a few hundred is normal — and mean "this sentence is long"
rather than "this is broken".

## The four conventions a patch is judged on

**Every rule traces to a finding.** The chain is: evidence in
[`docs/knowledge-base/`](docs/knowledge-base/README.md) with a confidence tag → a numbered rule in
[`DESIGN-RULES.md`](docs/DESIGN-RULES.md) → code with the rule ID in a comment → a lint rule that
fails the build. If you add behaviour that is not traceable to a finding, say so explicitly rather
than inventing a rule ID for it.

**A missing check never looks like a passed check.** `None` means unverified, not fine. If you add
something that can fail to run, make its absence visible in the artefact.

**Nothing vanishes silently.** Every dropped block, every cut beat, every degraded task is
recorded with the rule that authorised it. If your change can remove something the listener would
otherwise have heard, it records that it did.

**Comments record what broke, not what the code does.** The most valuable prose in this repository
is the comments explaining that a two-line title straddling a column gutter silently flipped the
reading order, or that a manuscript's line numbers turned `recov-` / `19` / `ery` into `recov-19`.
If you are tempted to write `# increment the counter`, write nothing; if you fixed something real,
write what it was.

## Where you will be most useful

The **lint rules** are the best target. Two thirds of the design rules are prose that nothing
checks, and each new check is a small class with a fixture pair. It is bounded, verifiable work
with a clear definition of done — [how to add one][extending].

The **verbalizers** are similar: notation that is spoken wrongly, a failing test, a fix.

The **spacing scheduler** (`src/mimem/plan/spacing.py`) has property tests with hypothesis and is
the one genuinely interesting algorithm here, if you want something harder.

## Where you will not be

Please do not:

- **Rewrite prose across the repository** to be more consistent. The voice is deliberate and the
  comments encode history. A sweeping edit destroys more than it tidies.
- **Add a dependency** without saying what it replaces and why the standard library will not do.
  Two dependencies have already been removed from the plan after being examined.
- **"Simplify" a threshold or a guard** without reading the comment above it. Nearly all of them
  exist because a specific real paper broke.
- **Widen scope past the issue.** A pull request that fixes one thing is easy to review. A pull
  request that fixes one thing and also reformats four modules is not.

## Two traps specific to this codebase

**Absolute thresholds on relative scores select nothing.** Difficulty, importance and abstractness
are normalised *within* the document. A threshold like "importance above 0.5" only ever selects
the paper's own subject. This has caused a real bug twice. If you need a cut on one of those
scores, use a rank.

**Writing files through shell heredocs corrupts backslashes** in some environments — a doubled
`\b` arrives as a literal backspace and the regex silently never matches. Use your editing tools
directly, and check a regex you have written by printing its `repr()`.

## Provenance

If a model generated a meaningful part of the change, `Co-Authored-By` in the commit is the right
place to say so. Do not attribute work to a person who did not do it.

[extending]: https://jepegit.github.io/mimem/building/extending/
