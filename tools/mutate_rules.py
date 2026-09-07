"""Is each lint rule actually protected by a test? Break it and find out.

A rule's id appearing in a test file proves nothing -- it might be in an exclusion list, or a
string in an unrelated assertion. The only real question is: **if this rule silently stopped
working, would anything go red?** This answers it the only way it can be answered, by gutting
one rule's ``check()`` at a time, running the suite, and recording whether the suite noticed.

    uv run python tools/mutate_rules.py

It takes a few minutes -- one full test run per rule -- which is why it is a tool you run when
you want to know, and not part of CI.

**What it found the first time**, and the reason it exists: twenty-four of the thirty rules never
fire on either corpus document, because the output is good, and I read that silence as most of
the suite being unprotected. It was not. Twenty-nine of thirty were caught. Silence on correct
input says nothing about whether a test would catch the rule breaking, and the two questions are
easy to confuse.

Source files are restored after every iteration, including on failure. If you interrupt it, run
``git status`` -- a killed process can leave one rule gutted.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import pathlib
import re
import subprocess
import sys

#: Where the rules live, by the base class each file defines.
SOURCES: dict[str, tuple[str, str]] = {
    "src/mimem/lint/rules.py": ("mimem.lint.rules", "LintRule"),
    "src/mimem/lint/script_rules.py": ("mimem.lint.script_rules", "ScriptRule"),
    "src/mimem/lint/artefact_rules.py": ("mimem.lint.artefact_rules", "ArtefactRule"),
}

#: The signature every rule's check method has, whatever it reads.
CHECK = re.compile(r"( *)def check\(self, [a-z]+: \w+\) -> list\[Violation\]:\n")

MUTANT = "return []  # MUTANT\n"


def rules() -> list[tuple[str, str, str]]:
    """``(rule_id, class_name, source_file)`` for every concrete rule, found by reflection."""
    found: list[tuple[str, str, str]] = []
    for path_name, (module_name, base_name) in SOURCES.items():
        # importlib, not `from mimem.lint import script_rules`: the package __init__ exports a
        # function of the same name, which shadows the module.
        module = importlib.import_module(module_name)
        base = getattr(module, base_name)
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, base)
                and obj is not base
                and not inspect.isabstract(obj)
                and getattr(obj, "id", None)
            ):
                found.append((obj.id, obj.__name__, path_name))
    return sorted(found)


def gut(path_name: str, class_name: str) -> None:
    """Make this one rule return no violations, whatever it is given."""
    path = pathlib.Path(path_name)
    text = path.read_text(encoding="utf-8")
    match = CHECK.search(text, text.index(f"class {class_name}("))
    if match is None:  # pragma: no cover - would mean the base signature changed
        raise SystemExit(f"no check() found for {class_name}")
    at = match.end()
    path.write_text(text[:at] + match.group(1) + "    " + MUTANT + text[at:], encoding="utf-8")


def restore() -> None:
    subprocess.run(["git", "checkout", "--", *SOURCES], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        help="a test path to exclude, e.g. to ask what the suite catches *without* one file",
    )
    parser.add_argument("--only", help="check a single rule id")
    args = parser.parse_args()

    targets = [r for r in rules() if not args.only or r[0] == args.only]
    if not targets:
        raise SystemExit(f"no rule matching {args.only!r}")

    unprotected: list[str] = []
    for index, (rule_id, class_name, path_name) in enumerate(targets, start=1):
        gut(path_name, class_name)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/", "-q", "--no-header", "-x"]
                + [f"--ignore={p}" for p in args.ignore],
                capture_output=True,
                text=True,
            )
        finally:
            restore()
        caught = result.returncode != 0
        if not caught:
            unprotected.append(rule_id)
        print(
            f"  [{index:2}/{len(targets)}] {rule_id:9} {'caught' if caught else 'NOT CAUGHT'}",
            flush=True,
        )

    print(f"\nunprotected: {len(unprotected)}/{len(targets)}")
    print("   ", " ".join(unprotected) or "(none)")
    return 1 if unprotected else 0


if __name__ == "__main__":
    raise SystemExit(main())
