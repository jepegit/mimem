---
icon: lucide/git-pull-request
---

# Adding to it

Four things you might want to add, and what each one costs. All of them are small; the
conventions around them are the part worth reading.

## Getting set up

```bash
uv venv --python 3.13 && uv pip install -e ".[dev,epub,llm]"
```

```bash
uv run pytest && uv run ruff check . && uv run mypy
```

`mypy --strict` and `ruff` are both clean and both run in CI on Ubuntu and Windows across Python
3.11 and 3.13. Keep them that way — several real bugs in this codebase were found by the type
checker, including one in the API adapter that no test could have caught.

## A new source format

Write an adapter in `ingest/`, register it, and stop. Nothing downstream may learn that your
format exists.

```python
class DocxAdapter(Adapter):
    name = "docx"
    version = "1"
    extensions = frozenset({".docx"})

    def load(self, path: Path) -> Document:
        ...  # produce Blocks with kind, role, text, order, page
```

The contract is that you return `Document` and assets. If your format tempts you to add a branch
in `clean/` or `plan/`, the temptation is a design smell — normalise it in the adapter instead.

## A new lint rule

This is the highest-value contribution available, because a rule that is checked is a rule that
is real.

```python
class SentencesEndSomewhere(ScriptRule):
    """SENT-09: a beat never ends on a conjunction.

    A listener who hears a beat end on "and" waits for the rest of it, and the pause that
    follows lands in the middle of their attention rather than at the end of it.
    """

    id = "SENT-09"
    description = "beats do not end on a conjunction"

    def check(self, script: Script) -> list[Violation]:
        return [...]
```

Then add it to `SCRIPT_RULE_TYPES` and give it a fixture pair in
`tests/unit/test_script_lint.py` — a mutation of a real plan that breaks it. The test suite
asserts that *every* rule has one, so a rule without a failing example will not merge.

Three conventions:

- **The ID is the rule ID** from [the design rules](../DESIGN-RULES.md). If your rule is not in
  that document, add it there first, with the finding behind it.
- **Recompute what you need from the beats.** Never read a field the planner filled in to record
  its intention. A linter that trusts the planner tests that the planner is self-consistent,
  which is not the property anyone wants.
- **Error or warning is a real decision.** Error means the build stops. Reserve it for things the
  generator could have avoided; use a warning for things that are properties of the source.

## A new elaboration task

```python
def example(concept: Concept, support: list[str], document: str) -> Request:
    """A worked micro-example (rule DIF-02).

    *Degrades to:* omitted.
    """
    return Request(
        task="example",
        system=SYSTEM,
        document=document,
        instruction=f"...",
        schema=ExampleOut,
        effort=EFFORT_HIGH,
    )
```

Four things are required of a new task, and the fourth is the one people skip:

1. **A strict output schema** in `llm/schemas.py`. No free-text parsing anywhere.
2. **A documented degradation path** in the docstring, in the form above. It is what makes
   partial failure survivable.
3. **A place in `DIF-02`'s spending order** in `elaborate/run.py`. Order is not cosmetic — an
   image before an explanation is an image of nothing.
4. **A decision about the grounding gate.** Does your task make claims *about the document*
   (checked for numbers, years, names and directions against its spans) or is it *ours* (numeric
   check only, and it must be announced as ours when spoken)? Getting this wrong either lets an
   invention through or rejects every good anchor.

Test it with `ScriptedClient`, which answers by task name. Do not key tests on the request
digest — it depends on every character of the prompt, so rewording an instruction would break
tests that are about something else.

## A new design rule

The rule comes last, not first.

1. **Find the evidence.** Add it to the relevant [knowledge base](../knowledge-base/README.md)
   file with a confidence tag — `[A]` well replicated, `[B]` reasonable, `[C]` thin — and an
   effect size where one exists. Every entry ends in an *implication*.
2. **Write the rule** in [`DESIGN-RULES.md`](../DESIGN-RULES.md) with an ID in the right family,
   and say who enforces it: config, planner, prompt, or lint.
3. **Implement it**, naming the ID in a comment.
4. **Check it**, if it can be checked.

A rule that cannot be traced back to a finding should not be a rule. A rule that cannot be
checked is a hope, and the document says which ones those are.

## House style

The codebase has a voice, and matching it is part of a good patch.

**Docstrings explain the decision, not the mechanics.** `def merge(...)` does not need "merges
two registries". It needs "regeneration merges rather than overwrites, because a registry that
silently reverts the moment you re-run is a read-only file with extra steps".

**Comments record what broke.** Most of the non-obvious code here exists because a real paper
broke it, and the comment says which paper and how. Those comments are the most valuable prose in
the repository — they are what stops the next person from "simplifying" the fix.

**Tests are named as claims.** `test_a_flipped_direction_is_caught`, not `test_check_2`. The name
should say what would be broken if it failed.

**Numbers get a reason.** A threshold with no comment is a threshold nobody can tune. If you
cannot say why it is 0.55 rather than 0.5, that is a sign it should be a rank rather than a
threshold — which is exactly what happened to the anchor selection.
