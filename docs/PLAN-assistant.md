# Plan — making mimem useful today, from an assistant

**Status:** planned and built, 2026-09-06. Ten tools, three prompts, and a review log; verified over a real stdio transport in `tests/unit/test_assistant.py`.

Part 1 produces a script. Part 2 — synthesis, playback, review across sessions — is not built.
That leaves a gap: today mimem is useful to someone who can run a Python CLI *and* assemble the
rest of the pipeline themselves. This plan closes as much of that gap as can be closed without
building an app, by using an assistant the user already has as the missing pieces.

---

## 1. What is actually missing

A programme needs two things mimem does not provide.

**A voice.** No assistant can be one. `audio.md` still has to reach a speech engine, and that is
milestone M7. Nothing in this plan changes it.

**A tutor who comes back tomorrow.** `cards.json` and the exposure log exist precisely so
something can schedule them. An assistant is a perfectly good tutor: it can ask, wait, judge and
record. This is the part an assistant can genuinely be.

There is also a third gap that is not about the product at all: **you have to be able to run a
CLI.** For a researcher with a PDF and a Claude subscription, that is the whole barrier.

## 2. Three unlocks

**Nobody has to run a command.** "Make me a study programme from this paper" builds it.

**The elaboration layer becomes free.** Stage 6 currently needs an Anthropic API key and costs
around $1.67 for a paper. If the host model writes the glosses, anchors and analogies instead,
the cost is the subscription the user already has, and the last paid dependency disappears.

**The cards become a habit.** A study session in chat, with the answers recorded, is the first
real piece of Part 2 — and the reason any of this was built.

## 3. Alternatives considered

| | What it is | Verdict |
|---|---|---|
| **A. Skills only** | A skill teaching an assistant to drive the `mimem` CLI | **No.** Claude Desktop has no shell. A skill alone works in Claude Code and nowhere else the user asked about. Still worth having *alongside* the server. |
| **B. Local MCP server over stdio** | `uvx mimem-mcp`, configured once in the host | **Yes.** Works in Claude Desktop, ChatGPT Desktop, Claude Code, VS Code and Cursor. The document never leaves the machine. |
| **C. `.mcpb` bundle** | A zip with a manifest; double-click to install | **Now the only way in** — see the note below §4.|
| **D. Remote hosted MCP** | A server we run; ChatGPT *web* can reach it | **No.** It would mean uploading papers that are frequently not ours to redistribute, and running infrastructure for a tool whose whole value is local. Revisit if there is demand. |
| **E. MCP Apps / embedded UI** | An interactive panel inside the client | **Not now.** Real value for a study session eventually, but it is a second product surface before the first one has users. |
| **F. Non-assistant exits** | Anki export, a TTS adapter, a static player | **Later, and separately.** Anki export is small and valuable; TTS is M7. Neither is on this plan's critical path. |

**Chosen: B, then C, plus a skill.** One server, configured by hand at first, plus a skill so
Claude Code gets the same workflows through the CLI it already has.

## 4. The design decision that matters

MCP has a primitive for exactly what stage 6 needs: **sampling**, where the server asks the
client to run a completion. It is the right tool and **no relevant client implements it** —
not Claude Desktop, not Claude Code.

So the elaboration layer becomes a round trip through the conversation instead:

```
elaboration_plan(programme)   ->  the concepts needing work, each with the source
                                  sentences and the same instructions the API path uses
   ...the assistant writes them...
apply_elaborations(answers)   ->  validated against the schemas, checked against the
                                  source, applied, and every rejection reported
```

This is not a workaround that gives something up. **The grounding gate still runs.** A gloss
claiming a number the paper never states is rejected by mimem's own deterministic check
(`GRD-03`), whatever wrote it — so the safety property does not depend on the assistant behaving
well. And the user watches it happen, which the API path does not offer.

If sampling ever lands, it becomes an optimisation, not a rewrite.

## 5. The tool surface

Nine tools, named for what a person wants rather than for pipeline stages.

| Tool | |
|---|---|
| `build_programme` | A PDF **path**, a **URL**, or **the text itself** to a finished programme. Returns a summary and the lint verdict, never the text. |
| `list_programmes` | What has been built, with dates and durations. |
| `read_programme` | The outline by default; one section at a time on request. |
| `elaboration_plan` | The stage 6 tasks, with their source sentences and instructions. |
| `apply_elaborations` | Validate, ground-check, apply, and report every rejection. |
| `study_session` | What is due, across programmes. |
| `grade_card` | Record how it went and schedule the next one. |
| `explain_beat` | Which rule produced this, and which sentence is behind it. |
| `set_concept` | Correct a ranking or a definition; it survives every future run. |

Plus three **prompts** — the workflows, so the assistant does not have to invent them: build a
programme, run a study session, improve a programme.

## 6. Constraints the design has to respect

**Context is the scarce resource.** A hundred-minute programme is fifteen thousand words. A tool
that returns `audio.md` would fill the conversation and leave no room for the conversation. Every
tool returns a summary; text comes a section at a time, with a hard cap, and the caps are stated
in the tool descriptions so the assistant can plan around them.

**The document must not leave the machine.** That is why this is a local server, and it is why
option D is rejected rather than deferred.

**Writes are confined; reads are not.** The user wants to point it at any PDF on their disk, so
reads are wherever they say. Everything written goes under one workspace directory
(`MIMEM_WORKSPACE`, default `~/mimem`), so nothing is ever scattered and everything can be
deleted in one go.

**Fetching is explicit and bounded.** A URL source is a network request the user asked for, over
http(s) only, with a size cap, and the tool says it fetched.

## 7. The review store

This deliberately crosses a stated Part 1 non-goal ("no cross-session scheduling"), because
scheduling is the point of the whole project and a session that forgets you is not a study
session.

Kept minimal and honest:

- **An append-only JSONL log** at `~/mimem/reviews.jsonl` — one line per answer, with the card,
  the programme, the timestamp, the grade and the interval used. Inspectable in a text editor,
  like everything else here.
- **A deliberately dull scheduler**: first correct answer in a day, then multiply the interval by
  the profile's ratio; a wrong answer resets to a day. It is not SM-2 and does not pretend to be.
- **The log records more than the scheduler uses**, so a better scheduler can be fitted to real
  data later rather than guessed at now.

## 8. What could go wrong

Written before building, and each one has a countermeasure in the design above.

| Risk | Countermeasure |
|---|---|
| Tools flood the context and the session becomes unusable | Summaries by default, sectioned reads, hard caps, caps documented in the tool descriptions |
| The user's PDF is a chat attachment, not a file on disk | Accept a URL as well as a path; say plainly in the docs that the file must be reachable |
| The assistant invents an elaboration when it lacks the source | Schema validation, then the same grounding gate the API path uses; rejections are reported, not silently dropped |
| The review scheduler is bad and becomes impossible to change | The log is richer than the scheduler; the algorithm is one small function with its own tests |
| The server writes files in surprising places | One workspace directory, configurable, never outside it |
| `.mcpb` packaging drifts from the manifest spec | A build script and a CI check that the bundle can be produced |
| Someone expects this to work in ChatGPT on the web | Said explicitly in the docs: web clients reach hosted servers only |
| The MCP SDK moves under us | Pinned in an extra, and the SDK's v1-to-v2 rename was already caught once during planning |
| A stray `print` corrupts the protocol stream | A dedicated entry point that never imports the console; logging to stderr; a test that asserts stdout stays clean on import |

## 9. What reviewing this plan changed

Five things did not survive a careful read, and they are the useful part of having written it
down first.

**`uvx mimem-mcp` does not work, because mimem is not on PyPI.** The whole "one line to install"
premise rested on a package that does not exist. The honest line today is

```
uvx --from git+https://github.com/jepegit/mimem mimem-mcp
```

which needs no publishing and works now. Publishing to PyPI is a decision for the repository's
owner, not a step in this plan.

**The `.mcpb` bundle is a second project.** A Python bundle has to carry its dependencies, and
one of mimem's is PyMuPDF — a large, platform-specific binary wheel. That is either a fat
per-platform bundle or a thin launcher that shells out to `uv` anyway. Either is defensible;
neither should block the server that has to work underneath it. Demoted to §11.

> **Overturned, and by the worst kind of evidence: a user who followed these instructions and got
> nothing.** On current Claude Desktop, `claude_desktop_config.json` is owned by the application
> and rewritten on exit, so a hand-added `mcpServers` entry disappears at the next start —
> silently, with no error to read. Extensions are the supported route, which makes the bundle the
> *only* way in rather than polish on top of one.
>
> The packaging objection turned out to be answerable in a line. The bundle carries no code: the
> manifest runs `uvx --from git+…`, so `uv` resolves PyMuPDF's wheel on the user's own machine for
> the user's own platform. Neither a fat bundle nor a launcher I had to write — `packaging/` is a
> manifest, an icon and a build script. It also buys something the JSON never could: the manifest
> declares `user_config`, so the workspace directory and the listener file get a settings form
> instead of a documented environment variable.

**The source is often not a file path.** Someone in Claude Desktop has the paper as a chat
attachment: the assistant can read it and cannot tell you where it is. So `build_programme` takes
a path, *or* a URL, *or* the literal text — the last of which costs almost nothing, because
mimem already has a text adapter.

**Nothing may print to stdout.** An MCP stdio server speaks protocol on stdout, and one stray
`print` or `rich` banner corrupts the stream in a way that presents as an unexplained
disconnection. That rules out reusing the typer CLI as the entry point: the server gets its own,
which never imports the console, and all logging goes to stderr.

**"The same grounding gate runs" has to be true, not nearly true.** The check currently lives
inside stage 6's private task runner. If the MCP path reimplements it, the two will drift and the
claim quietly becomes false. So the accept-or-reject step is lifted into one public function that
both paths call.

## 10. Out of scope, on purpose

- **Speech synthesis.** Still M7. The programme is still text at the end of this.
- **A GUI.**
- **Multi-user anything.**
- **Anki export.** Small and worth doing; not on this path.

## 11. Next, after this

- **Publishing to PyPI**, which turns the install line into `uvx mimem-mcp`.
- **Speech**, which is still M7 and still the thing that makes a programme a programme.
- **Anki export**, for people who already have a review habit and do not want another one.

## 12. Done when

- One file installed in Claude Desktop, or one command in ChatGPT Desktop, and the tools appear.
- A paper can be built, elaborated by the host model, and studied — with the grounding gate
  rejecting an invented number in a test.
- The review log survives a restart and the scheduler has its own tests.
- A documentation page walks a non-programmer through it.
