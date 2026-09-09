---
icon: lucide/brain-circuit
---

# Using a model with mimem

**None of this is required.** mimem's whole argument is that structure matters more than
fluency, and the structure is deterministic: a document goes in and a listenable, checkable
programme comes out with no model involved at all. What a model adds is the explaining — a
one-line gloss, a concrete anchor, an analogy that says where it breaks down, a description of a
figure you cannot see — and one thing that is not explaining at all: cutting the paper's longest
sentences into ones you can hold in your head.

Start here:

```bash
uv run mimem doctor
```

It says what is reachable from your machine and, for everything that is not, the exact next
thing to type. On a machine with nothing configured it looks like this — which is a real run,
on the machine mimem is developed on:

```
text generation
  assistant  ready         no key needed; the model is the conversation
  anthropic  no key
             -> export ANTHROPIC_API_KEY=sk-ant-...
  openai     no key
             -> export OPENAI_API_KEY=sk-...
  local      missing       nothing listening on 11434, 1234, 8080, 8000
             -> ollama serve   (or start LM Studio / llama-server / vLLM)

speech
  silent     ready         always available; makes shaped silence
  sapi       ready         9 voices installed
  piper      missing       not on PATH
  openai     no key

tools
  ffmpeg     ready         available for converting audio.wav
  uv         ready         the extension needs it at first start
```

`mimem doctor --live` sends one tiny structured request to each configured provider, because
*the key is set* and *the key works* are different claims.

## Four ways in, in the order most people should try them

| | Needs | Cost | Page |
|---|---|---|---|
| **The assistant** | Claude Desktop, Cursor, or any MCP host | nothing | [Without a key](no-key.md) |
| **A local model** | Ollama or similar, a few GB of disk | nothing | [Local models](local.md) |
| **An API** | a key | cents per paper | [Hosted APIs](api.md) |
| **Nothing at all** | — | nothing | [Without a key](no-key.md) |

The assistant route is first on purpose. It inverts the problem: the model is the conversation
you are already in, so there is no key, no billing and no provider to configure. It is not a
workaround for people who cannot afford an API — for most users it is simply the best option.

## What a model is and is not allowed to do

The division is the whole safety argument, and it is worth knowing before you turn any of this
on:

**Deterministic code owns every fact.** Numbers, units, symbols, what gets dropped, what comes
back and when — none of that is ever a model's decision. Rule `NUM-01` and the verbalizers own
values; the planner owns structure.

**A model owns prose, and every sentence it writes is checked.** Every number in a generated
sentence must appear in the source sentences it was written from; a claim that reverses the
paper's direction is rejected before it reaches the programme (`GRD-03`). You can watch that
happen — the elaboration report lists what was accepted, what was rejected and why.

**One task rewrites the paper's own words, and only one.** Rule `SENT-01` caps a sentence at
thirty-five spoken words, because a sentence you would re-read on the page is simply lost in
audio — and 465 sentences across a twelve-paper corpus are over it. The rule says what to do
about them: *long source sentences are split, not compressed.*

That distinction is the whole of it. A summary of a sentence reads exactly like a split of it,
and the listener has no way to tell which they were given. So the check runs in **both**
directions: every number in the source must appear in the split, and every number in the split
must appear in the source. Nothing else a model writes here can fail the first of those, because
nothing else is supposed to be lossless. It is what makes this safe to do to a paper's sentences
at all.

The paper is never edited. The split is stored beside the sentence it replaces, the span still
points at what was written, and `study.md` can show you one against the other. When a split
drops a value it is rejected and the long sentence is spoken as it stands — which happened twice
in ten on the first live run, and a long true sentence beats a short lossy one every time.

**When the model is absent, every task degrades along a documented path** and the manifest
records *why* — there are four different reasons and they need four different actions from you:
no provider configured, configured but unreachable, reached but refused the shape, or out of
budget. A run with no provider at all says so once rather than once per task. A gloss falls back to the paper's own definitional sentence; an anchor is omitted
rather than invented; a figure falls back to its caption. That is why `--local` is the default
and why a forgotten flag cannot start billing you.

## Was it worth it?

```bash
uv run mimem compare paper.pdf --fixtures fixtures/paper
```

Builds the document twice — once deterministic, once with the model — and diffs the result. The
deterministic build is the control; the difference is what you paid for.

```
gloss_coverage      0.182 -> 0.273  (+0.091 better)
concepts_spaced     0.545 -> 0.364  (-0.181)
cards               10 -> 7         (-3)
prompts_per_minute  0.831 -> 0.697  (-0.134)
the model wrote: 1 analogy, 1 anchor, 1 gloss, 1 why
cost: $0.0000 over 0 calls
```

**That shape is worth understanding before you spend anything.** More terms get defined — and
the explaining costs duration, which comes out of the same budget as the questions. Fewer cards,
fewer prompts per minute, ideas coming back less often. Retrieval practice is the second-largest
effect in [the knowledge base](../knowledge-base/01-core-effects.md), so a build that explains
more and asks less is not automatically a better one.

Whether that trade is right depends on the document and on you. The point of the command is that
it is now a number you can look at rather than an impression.

## Which implementation answers each task

Each task can be set to one of three modes in the profile:

| Mode | What happens | For |
|---|---|---|
| `off` | the deterministic path only; the model is never called | a task whose rules you trust |
| `assist` | the rules answer first; the model is asked only about what is left | paying for recall, not precision |
| `prefer` | the model answers, and the rules catch what it does not | the default |

Everything defaults to `prefer`. `gloss` looked like the obvious `assist` candidate — it is the
one task with two real implementations — and that was tried and reverted, because the two do not
produce the same thing: the rules write the pre-load's one line, the model writes that *and* the
full introduction. Skipping the call because a short definition already existed would have given
a paid run less for the same money, silently. It is offered, not assumed.

## Cost, briefly

`--dry-run` prints the planned calls and an estimate without making any. `--budget 2.00` stops
the run rather than surprising you. Both work with every provider.

A model is called at most a few dozen times per paper — once per concept that earns an
elaboration, once per figure, once per verification — and the source document is sent as a
cached prefix, so the second task on a document costs a fraction of the first.

!!! warning "The live API adapters have had limited exercise"

    The Anthropic adapter has never been run against a real key: there was none in the
    environment it was written in. The OpenAI-compatible adapter is tested thoroughly against a
    fake server — the schema negotiation, the retries, the error paths — but has not been run
    against a real OpenAI or Ollama server either. The assistant route and the whole
    deterministic pipeline *are* exercised. Try any API path on one short paper before pointing
    it at a book, and please report what happens.
