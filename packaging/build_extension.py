"""Build ``mimem.mcpb``, the one-file install for Claude Desktop and other MCP hosts.

An ``.mcpb`` is a zip with a ``manifest.json`` at its root. The manifest tells the host how to
start the server; the host gives the user a settings form for whatever the manifest declares as
``user_config``, which is how the workspace directory and the listener file get set without
anyone editing JSON.

**Why this exists at all.** The install instructions used to say "add mimem to ``mcpServers`` in
``claude_desktop_config.json``". On current Claude Desktop that file is owned by the application
and rewritten when it exits, so a hand-added server silently disappears on the next start -- which
is exactly what it looked like: nothing, twice. Extensions are the supported route now, and this
is the only way in.

**Why the bundle carries no code.** ``PLAN-assistant.md`` deferred a bundle partly because a
Python one would have to carry PyMuPDF's platform wheels, which is a release matrix rather than a
file. It does not have to: the manifest runs ``uvx --from git+https://github.com/jepegit/mimem``,
so ``uv`` resolves and installs on the user's own machine, for their own platform, at first start.
The bundle is a manifest and an icon. It needs ``uv`` on the PATH, which the documentation already
asks for.

Run it with ``uv run python packaging/build_extension.py``. The result lands in ``dist/``.
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
DIST = ROOT / "dist"
BUNDLE = "mimem.mcpb"

#: Files that go into the bundle, in order. Everything else in ``packaging/`` is build machinery.
CONTENTS = ("manifest.json", "icon.png")


def project_version() -> str:
    """The version from ``pyproject.toml``, so the bundle can never claim a different one."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if match is None:
        raise SystemExit("no version in pyproject.toml")
    return match.group(1)


def check(manifest: dict[str, object]) -> list[str]:
    """Everything that would make a host refuse the bundle, or accept it and do nothing."""
    problems: list[str] = []
    for field in ("manifest_version", "name", "version", "description", "server"):
        if not manifest.get(field):
            problems.append(f"manifest is missing {field!r}")

    server = manifest.get("server")
    config = server.get("mcp_config") if isinstance(server, dict) else None
    if not isinstance(config, dict) or not config.get("command"):
        problems.append("server.mcp_config needs a command")

    declared = manifest.get("version")
    if declared != project_version():
        problems.append(f"manifest version {declared} != pyproject {project_version()}")

    for name in CONTENTS:
        if not (PACKAGING / name).exists():
            problems.append(f"packaging/{name} does not exist")
    return problems


def build() -> Path:
    manifest = json.loads((PACKAGING / "manifest.json").read_text(encoding="utf-8"))
    problems = check(manifest)
    if problems:
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        raise SystemExit("bundle not built")

    DIST.mkdir(parents=True, exist_ok=True)
    out = DIST / BUNDLE
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name in CONTENTS:
            bundle.write(PACKAGING / name, name)
    return out


if __name__ == "__main__":
    path = build()
    size = path.stat().st_size
    print(f"wrote {path.relative_to(ROOT)} ({size:,} bytes)")
    print("install it: Claude Desktop -> Settings -> Extensions -> Install extension")
