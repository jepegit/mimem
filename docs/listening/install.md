---
icon: lucide/download
---

# Getting it running

Three commands, and none of them need you to understand Python. If something goes wrong, the
last section of this page is probably it.

## What you need first

**Python 3.11 or newer.** Check by opening a terminal and running:

```bash
python --version
```

If that says 3.11 or higher, you are fine. If it says "command not found" or a lower number, get
Python from [python.org](https://www.python.org/downloads/) — the standard installer, defaults
are fine. On Windows, tick *"Add Python to PATH"* on the first screen; it saves an argument
later.

**uv**, which installs the rest. It is one command:

=== "macOS / Linux"

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

=== "Windows"

    ```bash
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

You can use plain `pip` instead if you prefer; `uv` is faster and keeps the dependencies out of
your system Python, which is worth having.

## Install mimem

```bash
git clone https://github.com/jepegit/mimem.git
```

```bash
cd mimem && uv venv --python 3.13 && uv pip install -e ".[dev,epub]"
```

That last command makes a private environment for mimem and installs it. The `epub` part is
optional and adds EPUB support; drop it if you only care about PDFs.

Check it worked:

```bash
uv run mimem version
```

You should see a version number and the file formats it can read.

!!! tip "Every command on this site starts with `uv run`"

    That is just "run this inside mimem's own environment". If you would rather type `mimem`
    on its own, activate the environment first — `source .venv/bin/activate` on macOS and Linux,
    `.venv\Scripts\activate` on Windows — and then drop the `uv run` from everything.

## Optional: the elaboration layer

mimem works without any AI model, and that is the default. The optional layer adds glosses,
concrete images and analogies, and it calls a paid API.

```bash
uv pip install -e ".[llm]"
```

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Nothing is billed unless you pass `--llm`, and `--dry-run` will tell you the cost before you
spend it. See [tuning](tuning.md#the-elaboration-layer).

!!! warning "This path has not been road-tested"

    The code that talks to the API was written and type-checked but never actually run — there
    was no API key in the environment it was built in. Try it on one short paper before pointing
    it at a book, and please open an issue if it misbehaves.

## Optional: better concreteness scores

mimem decides which ideas need a concrete image partly from how *imageable* the words are. Out of
the box it guesses this from word endings — English marks abstraction in its suffixes — which
works but is blunt.

For measured scores, download the [Brysbaert concreteness
norms](http://crr.ugent.be/archives/1330) (a free CSV of human ratings for ~40 000 English words)
and put it at `data/concreteness.csv`, or point `MIMEM_CONCRETENESS_FILE` at your copy. It is not
bundled because it is someone else's dataset with its own terms.

`mimem concepts` tells you which source is live on every run, so a guess never looks like a
measurement.

## When it goes wrong

??? failure "`command not found: uv`"

    The installer put `uv` somewhere your terminal is not looking. Close the terminal and open a
    new one — that fixes it most of the time. If not, the installer printed a line about adding
    a directory to your `PATH`; that is the one to follow.

??? failure "`No solution found when resolving dependencies`"

    Your Python is older than 3.11. `uv venv --python 3.13` will fetch a newer one for you even
    if your system Python is old.

??? failure "It ran, but the output is a mess of nonsense words"

    Some PDFs have no real text in them — they are photographs of pages. Run
    `uv run mimem inspect paper.ir.json` and look at the word count: if it is near zero, or the
    text is gibberish, the PDF needs OCR first. mimem does not do OCR yet.

??? failure "It ran, but it missed half the paper"

    Run `uv run mimem inspect paper.ir.json --outline`. That prints the section structure it
    found and every complaint it had along the way. Two-column layouts, unusual heading fonts and
    manuscripts with line numbers are the usual culprits, and the diagnostics normally say so.
    An issue with the PDF attached is genuinely useful.

## Next

[Do your first paper](first-paper.md){ .md-button .md-button--primary }
