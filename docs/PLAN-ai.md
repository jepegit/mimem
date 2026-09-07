---
icon: lucide/brain-circuit
---

# Plan: where AI belongs, how to reach it, and how to work without it

**Status: proposed. Nothing in this document is built yet** except where it says otherwise.

Part one is complete: a document goes in and a playable programme comes out, and the only model
involved is optional. This plan is about the other half of the question — where a model makes
the result *better*, how a user actually connects one, how several are orchestrated, and what
happens on the machine where none of them are available.

That last case is not hypothetical. It is this machine, tonight:

```
ollama         -          ANTHROPIC_API_KEY  unset
llama-server   -          OPENAI_API_KEY     unset
lms            -          ELEVENLABS_API_KEY unset
jan            -          local servers      none listening
```

No key, no local runtime, nothing on a port. Everything in stage 6 degrades, and the programme
still builds, which is the design working. But it also means **the paths this project's own
author cannot currently exercise are most of them**, and a plan that ignores that ships a
feature nobody can turn on.

---

## 1. What exists today

| Where | What the model does | Provider | Ever run? |
|---|---|---|---|
| Stage 6, `elaborate` | gloss, anchor, analogy, why, compress | Anthropic only | **No** |
| Stage 6, figures | describe a rendered crop | Anthropic only | **No** |
| Stage 6, gate | entailment check (`GRD-02`) | Anthropic only | **No** |
| MCP assistant | *all of the above*, written in the conversation | none needed | **Yes** |
| Stage 9, `speak` | text to audio | silent / SAPI / Piper / OpenAI-compatible | **Yes** |

Four transports already sit behind one protocol — `NullClient`, `FixtureClient`,
`RecordingClient`, `AnthropicClient` — with a content-addressed cache, a cost estimator, a
`--budget` hard cap and a `--dry-run`. The machinery is in better shape than the reach: it can
do all the right things to exactly one vendor.

**The assistant route is the one that works**, and it works because it inverts the problem: the
model is the conversation the user is already in, so there is no key, no billing and no
provider. That is not a workaround. It is the best available answer for a large class of user
and this plan should protect it, not treat it as a stopgap.

---

## 2. Where AI belongs, and where it must not

The project already has a rule for this and it is a good one: **deterministic code owns every
fact; a model owns prose.** What is missing is the next distinction, which is between a model
that *writes* and a model that *judges*. Those have opposite risk profiles and the design
should stop treating them as one thing.

### The three roles

**Author.** The model produces text that reaches the listener. Highest risk — a fluent wrong
sentence is the worst output this system can make — and every output must pass the grounding
gate. Currently: gloss, anchor, analogy, why, compress, figure.

**Critic.** The model reads output the deterministic pipeline produced and says what is wrong
with it. Low risk: its output is a report, not a script, and a wrong criticism costs a human
thirty seconds. **Almost entirely unused today**, and it is the cheapest available win.

**Author of tooling.** The model writes *code* — a lint rule, a fixture, a test — which is then
reviewed, type-checked and committed. Zero runtime risk, because nothing it produces reaches a
listener without passing through the same gates as hand-written code. See §6.

### Stage by stage

| Stage | Role for AI | Position |
|---|---|---|
| 1 ingest | none | A PDF parser is not a language problem. Layout models exist; PyMuPDF plus the drop report is cheaper and auditable. |
| 2 clean | **critic** | "Does this block boundary look wrong?" is a good question to ask a model about 20 sampled blocks; a bad answer costs nothing. |
| 3 triage | none as author, **critic** | What to drop must stay deterministic and reported. But "here is what was dropped — did anything important go?" is exactly a critic's job. |
| 4 concepts | **assist** | Ranking is deterministic and measurable. A model proposing *additional* candidates, scored by the same scorer, is safe and probably better. |
| 5 verbalize | **none, ever** | Numbers, units, symbols. This is where a model would be most tempting and most dangerous. |
| 6 elaborate | **author** (as today) | Unchanged. |
| 6b definitions | **author, with the deterministic path as the verifier** | See §3 — this is the worked example. |
| 7 plan | none as author, **critic** | Structure is rules. But "does this section title describe this section?" is worth asking. |
| 8 render | none | Mechanical. |
| 9 lint | **critic, then codegen** | The centrepiece. See §6. |
| 9 speak | **author** (TTS) | A different kind of model; same adapter discipline. |

The pattern: **AI as critic is available at almost every stage and is used at none of them.**

---

## 3. Running both paths at once

The user's framing — *"some parts of our pipeline might play in parallel with the AI, and act as
backup if AI is missing"* — is right, and the current design only does half of it. Today each
task has a degradation path taken *when the model is absent*. The proposal is to make the
deterministic path a first-class participant that runs **whether or not** the model does.

### Why both, always

Because then the deterministic result is a **control**. Every paid run produces, for free, a
paired comparison on the same document: what the rules got, what the model got, and whether
they agree. That is a measurement the project currently cannot make, and it is the only honest
way to answer "is the model actually worth the money" — which is a question this project should
want to answer, given that its whole argument is that structure matters more than fluency.

### The reconciler

```
                    ┌── deterministic result ──┐
   task ────────────┤                          ├──► reconcile ──► used, and both recorded
                    └── model result ──────────┘
```

Three policies, set per task in the profile:

| Mode | Behaviour | For |
|---|---|---|
| `off` | deterministic only; the model is never called | the default, and `--local` |
| `assist` | both run; the model's result is used **only if** it passes the gate *and* the deterministic result is empty | tasks where the rules have high precision and low recall |
| `prefer` | both run; the model's result is used if it passes the gate | tasks the rules cannot do at all |

`assist` is the interesting one, and the definitions work is exactly its shape: the deterministic
finder has near-perfect precision and finds one or two terms a paper. A model would find ten with
unknown precision. Under `assist` the rules keep what they found, the model fills the gaps, and —
the part that matters — **the deterministic finder becomes a verifier for the model**: it can
check that the model's gloss is actually present in the sentence the model cited, using the same
`acceptable()` guards that were tuned on real papers.

That is the general shape worth aiming for. *Wherever a deterministic implementation exists, it
is not just the fallback: it is the test oracle for the model.*

### What "AI is missing" means precisely

Four different absences, currently collapsed into one:

1. **No provider configured** — no key, nothing on a port. Degrade, and say so once, not per task.
2. **Provider configured but unreachable** — network down, server not started. Degrade, and say
   *this is probably temporary*, because the fix is different.
3. **Provider reachable but refused** — quota, rate limit, safety refusal. Degrade, record the
   reason verbatim.
4. **Budget exhausted mid-run** — stop, and leave the artefacts already produced.

The manifest should distinguish these. "Degraded" currently covers all four and a user cannot
tell "you have no key" from "the server timed out".

---

## 4. Providers, and how a user connects one

The TTS layer in M7 settled this argument once already: **one adapter that speaks a widely
implemented shape reaches more engines than several vendor adapters.** `POST /audio/speech`
covers OpenAI, VoiceStudio and several self-hosted servers with twenty lines of `urllib`. The
same is true, more strongly, for chat completions.

### The adapter set

| Adapter | Reaches | Auth | Notes |
|---|---|---|---|
| `assistant` | Claude Desktop, Claude Code, Cursor, ChatGPT desktop, Continue, any MCP host | none | **Already built.** The model is the conversation. |
| `anthropic` | Claude models | `ANTHROPIC_API_KEY` | Already built; still never run. |
| `openai` | OpenAI, Azure OpenAI, Groq, Together, OpenRouter, DeepInfra, Fireworks | `OPENAI_API_KEY` or `--api-key` | **New.** `POST /v1/chat/completions` with JSON schema output. |
| `local` | Ollama, llama.cpp server, LM Studio, vLLM, Jan, text-generation-webui | none | **New** — but it is the *same adapter* as `openai` with a different `--base-url`, exactly as the TTS layer does it. A separate name because the defaults differ (no key, longer timeout, smaller context). |

Four names, two implementations. That is the whole point of the shape.

**Structured output is the one real portability problem.** The pipeline requires typed responses
(`GlossOut`, `FigureOut`, `VerifyOut` …), and providers disagree: Anthropic uses tools, OpenAI
uses `response_format: json_schema`, Ollama uses `format`, llama.cpp uses a GBNF grammar, and
several local servers support none of them. The adapter must therefore carry a **capability
declaration** and a documented ladder:

1. native JSON-schema mode if the server advertises it;
2. tool/function calling if not;
3. prompted JSON plus `pydantic` validation and one retry with the validation error appended;
4. if that fails twice, the task degrades — never a half-parsed object.

Step 3 is what makes small local models usable at all, and it must be honest about its failure
rate; the harness should record schema-retry counts per provider so "which local models actually
work" becomes a measured list rather than folklore.

### Speech providers

M7 shipped `silent`, `sapi`, `piper` and `openai`. To add:

- **`elevenlabs`** — named explicitly by the user, has its own API (`/v1/text-to-speech/{voice}`),
  not OpenAI-shaped, so it needs a real adapter. Best voices available; per-character billing, so
  the chunk cache matters more here than anywhere.
- **`kokoro`** — strong open-weights model, commonly served behind an OpenAI-compatible endpoint,
  so it may need no new code at all. Verify before writing any.
- **MP3 output**, now that `ffmpeg` turns out to be present on this machine. M7 rejected it
  because it would be a dependency; the right shape is: WAV always, MP3 *if* `ffmpeg` is on the
  PATH, never a requirement. A 20-minute programme goes from 50 MB to about 20.

### Documentation requirement

Every adapter above needs a page a user can follow without knowing anything about the project.
Per provider: what to install, where to get the key, the exact command, how to verify it worked,
what it costs, and what to do when it fails. §7 lists the pages.

---

## 5. Orchestration

### Concurrency

Stage 6 is currently a sequential loop over concepts. On a 98-page review that is 40–80 requests
at perhaps two seconds each. Bounded concurrency (default 4, `--concurrency`) turns three minutes
into forty seconds. The tasks are independent by construction — each concept's elaboration
depends only on its own support sentences — so this is a thread pool and a semaphore, not a
scheduler.

The exception is **verify-after-generate**: the gate must see the finished claim. That stays a
two-phase fan-out, not a pipeline.

### Model routing

The plan's existing position is right and should be kept: *a cheaper worker model is a measured
decision, not an assumption.* With the eval harness and a corpus this becomes testable — run the
same document with `--model` set differently and compare `grounded`, `values_kept`,
`gloss_coverage` and the entailment pass rate. The routing table should be **a profile setting
with measured numbers beside it**, not a constant in the source.

A sensible starting hypothesis, to be confirmed or refuted:

| Task | Hypothesis | Why |
|---|---|---|
| `compress` | small model | mechanical rewriting, output heavily constrained |
| `gloss` | small model | one line, verified against the source |
| `anchor`, `analogy` | large model | the output *is* the judgement; a bad analogy is memorable and wrong |
| `figure` | large multimodal | already demonstrated to fail subtly on real figures |
| `verify` | large model | it is the gate; a cheap gate is not a gate |

### Batching and cost

`estimate()` already takes a `batch` flag, so batch pricing was anticipated. Anthropic and OpenAI
both offer ~50% discounts for asynchronous batches with a latency cost measured in hours. That
suits exactly one use case — *"process my whole reading list overnight"* — which is a real one
for this project. Worth building **after** concurrency, and only with a queue the user can
inspect.

### The budget

`--budget` exists as a hard cap. Two additions: a **per-task breakdown** in the manifest (so
"why did that cost four dollars" has an answer), and a **pre-flight estimate that includes the
degradation cost of *not* running** — i.e. tell the user what they lose, not only what they pay.

---

## 6. Using LLMs to write the linters

This is the part of the request with the most upside, and it needs one distinction made
carefully.

**LLM-as-linter** puts a model in the build: every run asks it "is this script any good?".
Slow, costly, non-deterministic, and it makes CI depend on a vendor. **LLM-authored-linter**
uses a model once, offline, to write a Python rule that is then reviewed, type-checked,
committed, and runs forever in microseconds for nothing.

**The second is strictly better wherever it is possible, and the first is how you find out what
the second should say.** The pipeline is therefore a loop, not a service:

```
  corpus of programmes
          │
          ▼
   [critic pass]  ── model reads audio.md + study.md + DESIGN-RULES.md
          │           and answers: "what is wrong here that no rule catches?"
          ▼
    findings, clustered by hand
          │
          ▼
   [codegen pass] ── model writes a candidate ScriptRule from one finding
          │           plus a positive fixture and a negative fixture
          ▼
   [acceptance]   ── deterministic, non-negotiable (below)
          │
          ▼
     human review ──► committed rule
```

### Why the rules are an unusually good codegen target

They are already the right shape for it, which was not planned but is true:

- one class, one `check()` method, one rule ID matching a documented design rule;
- three narrow base classes (`LintRule` reads text, `ScriptRule` reads the plan, `ArtefactRule`
  reads the bundle) with a fixed signature;
- output is a list of `Violation`, a small dataclass;
- thirty rules already exist as worked examples, each with a docstring explaining *why*, which is
  the best possible few-shot prompt;
- the whole thing is `mypy --strict` and `ruff` clean, so two thirds of the failure modes of
  generated code are caught before a human looks.

### Acceptance criteria — the part that makes this safe

A generated rule is accepted into the candidate set only if **all** of these hold, checked
automatically:

1. it imports and type-checks under `mypy --strict`;
2. `ruff` passes;
3. it **fires** on the negative fixture it shipped with (a rule that never fires is not a rule);
4. it **does not fire** on the positive fixture;
5. it produces **no new violations across the existing corpus** — or, if it does, those are
   listed for a human, because a rule that fires on known-good output is either a real
   discovery or a false positive, and only a person can say which;
6. it is deterministic: same input, same output, twice.

Then a human reads it. Criterion 5 is the one that turns this from "generate plausible code" into
something trustworthy, and it only works because the corpus exists.

### The negative corpus

The blocker is criterion 3. Today there is no library of *deliberately bad* scripts, so a new
rule has nothing to prove itself against.

**This is worth building on its own, and the reason is measurable.** Running the whole suite over
both corpus documents:

| | |
|---|---|
| design rules documented | 91 |
| with a mechanical rule class | **30** |
| that fire on the corpus | **6** |
| checked, and permanently silent | **24** |
| never named in any test | 1 (`STR-08`) |

The 24 are silent because the output is *good*, which is the system working. But it means that
for four fifths of the suite, **a rule that broke would look exactly like a rule that passed.**
Test coverage is not the gap — 29 of 30 ids appear in the tests. The gap is that most rules have
no input that makes them speak, so nothing distinguishes "correct" from "no longer wired up".

That is a hole in the project today, independent of anything to do with AI, and it is the
prerequisite for trusting a generated rule.

### Rule mining as its own product

The critic pass has value even when no rule comes out of it. Running a model over ten programmes
and asking *"what would annoy a listener here?"* is the cheapest available source of design
feedback, and this project has never had any — every rule so far comes from the literature or
from one person noticing something. Findings that are too fuzzy to become rules still belong in
the plan as open questions.

---

## 7. Utilities, and the documentation they need

### `mimem doctor`

**The highest-value single command in this plan**, and the one this investigation argues for
most directly: on this machine, a new user would discover the absence of every provider one
confusing error at a time.

```
$ mimem doctor
text generation
  assistant       ready      no key needed; use the Claude Desktop extension
  anthropic       no key     set ANTHROPIC_API_KEY, or use --api-key
  openai          no key     set OPENAI_API_KEY
  local           none       no server on :11434, :1234, :8080  (try `ollama serve`)

speech
  silent          ready
  sapi            ready      9 voices, en-US default
  piper           missing    binary not on PATH
  openai          no key
  elevenlabs      no key

encoding
  ffmpeg          ready      MP3 output available
```

Every red line names the fix. It should also run a real one-token request against anything it
reports as ready, because "the key is set" and "the key works" are different claims and this
project has been burned by exactly that distinction once already.

### The rest

| Command | Does | Status |
|---|---|---|
| `mimem doctor` | the above | new |
| `mimem record <doc>` | one paid run → a reusable fixture set | `RecordingClient` exists, no CLI |
| `mimem compare <doc>` | build twice, deterministic vs model, diff the artefacts and the metrics | new; the §3 measurement |
| `mimem rule new "<english>"` | draft a rule + fixtures, run the acceptance checks, print the result | new; §6 |
| `mimem rule test` | every rule against the negative corpus — which rules still fire? | new; needs the corpus |
| `mimem critic <out>` | the critic pass over a built programme | new |

### Documentation pages

| Page | Contains |
|---|---|
| `docs/ai/index.md` | The map: what AI does here, the three roles, and the fact that none of it is required. |
| `docs/ai/no-key.md` | **First**, deliberately: everything that works with nothing configured. |
| `docs/ai/assistant.md` | The MCP route, extended past Claude Desktop: Claude Code, Cursor, ChatGPT desktop, Continue. One config block each, verbatim, tested. |
| `docs/ai/api.md` | Anthropic and OpenAI-compatible: key, command, cost, verification, failure modes. |
| `docs/ai/local.md` | Ollama, llama.cpp, LM Studio, vLLM — install, serve, point mimem at it, which models actually hold a schema. |
| `docs/ai/speech.md` | Extends the M7 audio page with ElevenLabs and MP3. |
| `docs/ai/cost.md` | What a paper costs on each provider, measured, with the dry-run command. |
| `docs/building/rules.md` | Writing a lint rule by hand, and with `mimem rule new`. |

Every one of these must be followable start to finish by someone who has not read the plan, and
each provider section ends with a command whose output the page shows, so a user can tell
whether it worked.

---

## 8. Milestones

**M8 — reach (1 week).** The `openai`/`local` adapter with the schema ladder, `mimem doctor`,
`mimem record`, and the four `docs/ai/` pages. *Done when:* a user with Ollama and no key can
run stage 6, and `doctor` told them how.

**M9 — both paths (0.5 week).** The reconciler, the three modes, the four absence kinds
distinguished in the manifest, `mimem compare`. *Done when:* one command reports what the model
changed and what it cost, on the same document.

**M10 — the negative corpus (0.5 week).** One broken script per rule; `mimem rule test`. *Done
when:* all thirty rules are known to still fire, not merely to stay silent.

**M11 — rule authoring (1 week).** `mimem critic`, `mimem rule new`, the acceptance checks.
*Done when:* one rule in the suite was drafted by a model, passed all six criteria, and was
reviewed and committed like any other.

**M12 — more voices (0.5 week).** ElevenLabs, Kokoro if it needs code, optional MP3.

M10 before M11 is not negotiable: the acceptance checks are the whole safety argument for
generated rules, and criterion 3 needs the corpus.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| **Provider sprawl** — six adapters, none well tested | Two implementations behind four names. Every adapter must be exercised by `doctor` against a real endpoint before it is documented. |
| **Local models cannot hold a schema**, and the failure looks like a mimem bug | The ladder in §4, the retry count recorded per provider, and a documented list of models known to work. Degrade rather than half-parse. |
| **Generated rules that look right** | The six acceptance criteria, and human review. No generated rule is committed by a machine. |
| **The critic becomes a build dependency** | It is a command, never part of `build`. CI must never call a model. |
| **Cost surprise** | `--budget` exists; add the per-task breakdown and make `doctor` print prices. |
| **The assistant route gets neglected** because API work is more interesting | It is the only path that works with nothing installed, and it is what the extension ships. It goes first in the docs for that reason. |
| **This plan is larger than part one was** | It is. M8 and M10 are the load-bearing ones; M11 is the speculative one and should be cut if the critic pass turns out to produce nothing worth writing down. |

---

## 10. What this investigation changed

Written after the survey rather than before it, in the manner of the figures plan.

**The absence is the finding.** I expected to be planning an upgrade to a working integration.
There is no working API integration: `AnthropicClient` has still never been run, there is no key
on this machine, no local runtime, and nothing listening on a port. The most useful thing in this
plan is therefore not an adapter — it is `mimem doctor`, because the current failure mode is a
user discovering each absence separately and concluding the project is broken.

**"Critic" was missing from the vocabulary.** The design has always divided work into *the
model writes prose* and *the code owns facts*, and that framing hid a third thing entirely: a
model reading finished output and saying what is wrong with it. That is cheap, safe, needs no
grounding gate, and is available at seven of the nine stages. It is now §2's centrepiece and it
was not in the original request.

**LLM-authored linters are a better idea than LLM linters, and the codebase is already shaped
for it.** The request said "utilize the strength of LLMs to produce linters", and my first
reading was a model judging scripts at build time. That is the worse half. The rules are small
typed classes with thirty worked examples and a strict type checker over them — an unusually
good codegen target — so the model's job is to write a rule *once* and never run again. The
runtime critic's job is to find out which rule is worth writing.

**The negative corpus turned out to be a prerequisite, and I had the argument for it wrong until
I measured.** I wrote that the suite could not tell whether its rules still fire, which is not
true: 29 of 30 rule ids are named in tests. The real number is sharper and worse. Thirty rule
classes cover 91 documented design rules, and on both corpus documents **only six of them ever
fire** — the other 24 are checked and permanently silent, because the output is good. For four
fifths of the suite a rule that broke would be indistinguishable from a rule that passed. That
is a hole that exists today, has nothing to do with AI, and should probably be filled before
anything else in this plan.

**Degradation is not one thing.** "The model was unavailable" currently covers no key, network
failure, quota refusal and budget exhaustion. Those need four different sentences, because they
need four different actions from the user.

**M7's WAV-only decision was right for the project and wrong for this machine.** The reasoning
was that MP3 means `ffmpeg`, which is a dependency and a platform matrix. `ffmpeg` turns out to
be installed here already. The resolution is not to reverse the decision but to soften it: WAV
always, MP3 when `ffmpeg` happens to be present, never a requirement.

**The deterministic path should be promoted from fallback to control.** This is the part I would
most want argued with. Running both paths on every AI-enabled build costs the model call
regardless, gives a free paired comparison, and makes the deterministic implementation the test
oracle for the model — which is exactly what the definitions work built without anyone planning
it that way. If that is right, it is the most valuable idea here and it changes what stage 6
*is*: not "the model's stage", but the place where two implementations check each other.
