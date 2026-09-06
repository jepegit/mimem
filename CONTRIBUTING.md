# Contributing

Yes, please. Genuinely — this is a project I built for myself and it gets better the more people
are in it. Nothing here is precious, nothing is off limits, and there is no contribution too
small to be worth making.

If you are not sure whether an idea is welcome, it is. [Open an issue][issues] and ask.

## The fastest useful thing you can do

**Run it on a paper from your own field and tell me what came out wrong.**

```bash
uv run mimem build your-paper.pdf --out out/paper
```

Then open `out/paper/audio.md` and read the first page aloud. Anything that made you stop — a
sentence that doesn't parse, a number said wrong, a section that vanished, an acronym nobody
expanded — is a bug. [Open an issue][issues] and paste it.

Every one of my test papers is batteries and electrochemistry. Whole categories of failure are
invisible to me because I do not read medical trials, or linguistics, or economics preprints. If
you do, you can find things I cannot.

Two commands that make a bug report easy to act on:

```bash
uv run mimem inspect out/paper/doc.ir.json --outline   # what ingestion actually saw
uv run mimem explain out/paper --beat t_4e4756d5592f   # why one beat exists
```

## Getting set up

You need Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/jepegit/mimem.git && cd mimem
uv venv --python 3.13 && uv pip install -e ".[dev,epub,llm,docs]"
```

```bash
uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy
```

All four should pass on a clean checkout. If they do not, that is a bug and I want to hear about
it before you spend an evening on it.

## Where the good first tasks are

**A lint rule.** This is the highest-value contribution available and one of the smallest. About a
third of the rules in [`docs/DESIGN-RULES.md`](docs/DESIGN-RULES.md) are mechanically checked; the
rest are prose. A rule that is checked is a rule that is real. Each one is a small class, a
message, and a fixture pair — [how to add one][extending].

**A verbalizer case.** Notation that is spoken wrongly: a unit, an identifier, a statistical
construct, a chemical formula, a Greek symbol used oddly. Add the case to
`tests/unit/test_verbalize.py`, watch it fail, fix it.

**A listener profile for your field.** `listener.example.yaml` is battery-shaped. A good
`domain_terms` and pronunciation lexicon for chemistry, biology, ML, medicine or economics makes
the tool immediately better for everyone in that field, and requires no Python at all.

**A source format.** DOCX, HTML, LaTeX are all sketched in the plan and unimplemented. One adapter
class, and nothing downstream may learn that your format exists.

**Documentation.** If a page confused you, that is the page's fault. Fixing it while the confusion
is fresh is worth more than my re-reading it for the fifth time.

## What I care about in a patch

The codebase has a voice and a few rules. None of them are about style for its own sake.

**Every rule traces to a finding.** A new design rule starts in
[`docs/knowledge-base/`](docs/knowledge-base/README.md) with the evidence and a confidence tag
(`[A]` well replicated, `[B]` reasonable, `[C]` thin), becomes a numbered rule in
[`DESIGN-RULES.md`](docs/DESIGN-RULES.md), then gets implemented with its ID in a comment, then
gets checked if it can be. A rule with no evidence behind it should not be a rule; a rule nothing
checks is a hope, and the document says which ones those are.

**Comments record what broke.** Most of the non-obvious code here exists because a real paper
broke it, and the comment says which paper and how. Those comments are the most valuable prose in
the repository — they are what stops the next person from "simplifying" the fix. If your change
fixes something real, say what it was.

**Docstrings explain the decision, not the mechanics.** `merge()` does not need "merges two
registries". It needs "regeneration merges rather than overwrites, because a registry that
silently reverts the moment you re-run is a read-only file with extra steps".

**Tests are named as claims.** `test_a_flipped_direction_is_caught`, not `test_check_2`. The name
should say what would be broken if it failed.

**A missing check never looks like a passed check.** Concreteness scores say whether they came
from measured norms or a guess. Groundedness verdicts are `None` when unverified, never `True`.
This one has teeth: it is why several things here are more verbose than they would otherwise be.

**`mypy --strict` and `ruff` stay clean.** Both run in CI on Ubuntu and Windows across Python 3.11
and 3.13. The type checker has found several real bugs in this codebase, including one no test
could have caught.

## Opening a pull request

Branch from `main`, make the change, and open it. There is no template and no checklist.

A good description says what broke and how you found it, more than what you changed — the diff
already says what you changed. If your patch came out of running mimem on a real document, saying
which document and what it did wrong is the most useful sentence in the PR.

CI runs the tests, the linter, the type checker and a documentation build. If it goes red on
something that looks unrelated to your change, say so rather than fighting it; it is probably mine.

I will read everything. I may be slow — this is a side project and I have a day job — but nothing
gets ignored.

## If you are an AI agent

You are welcome, and there is [a page written for you](AGENTS.md). Two asks: say so in the pull
request, and have a human who can answer questions about the change.

## Conduct

Be decent. Assume the other person is doing their best with the information they have. Disagree
about the work, not about the person.

If something goes wrong that needs a human, email me: jan.petter.maehlen@ife.no.

[issues]: https://github.com/jepegit/mimem/issues
[extending]: https://jepegit.github.io/mimem/building/extending/
