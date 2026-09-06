"""The extension bundle: the only way into Claude Desktop, so it has to keep building.

This is not a test of zip files. It is a test of the two ways the bundle goes wrong quietly:
the manifest drifts from what a host will accept, and the version drifts from the package's,
so someone installs "0.1.0" and gets whatever is on main.

The bundle is a manifest and an icon; the server it launches is fetched by ``uv`` at first start,
for the user's own platform. That is why there is no dependency matrix to test here — and why
there is a test that the launch command has not quietly become something else.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from mimem.assistant.workspace import WORKSPACE_ENV

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "packaging" / "manifest.json"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_the_manifest_has_what_a_host_requires(manifest: dict) -> None:
    for field in ("manifest_version", "name", "version", "description", "server"):
        assert manifest.get(field), f"missing {field}"
    assert manifest["server"]["mcp_config"]["command"]


def test_the_version_matches_the_package(manifest: dict) -> None:
    """Otherwise someone installs a version number that means nothing."""
    from mimem import __version__

    assert manifest["version"] == __version__


def test_the_launch_command_starts_the_server_we_ship(manifest: dict) -> None:
    """A bundle that installs cleanly and launches the wrong thing is the worst outcome."""
    config = manifest["server"]["mcp_config"]
    assert config["command"] == "uvx"
    assert "mimem-mcp" in config["args"], "the console entry point is what must be launched"
    assert "git+https://github.com/jepegit/mimem" in config["args"]


def test_the_settings_form_covers_what_the_server_reads(manifest: dict) -> None:
    """The point of a manifest over hand-edited JSON: the user gets a form, not a variable."""
    env = manifest["server"]["mcp_config"]["env"]
    assert WORKSPACE_ENV in env
    for placeholder in env.values():
        key = placeholder.removeprefix("${user_config.").removesuffix("}")
        assert key in manifest["user_config"], f"{placeholder} has no user_config entry"


def test_every_declared_tool_exists(manifest: dict) -> None:
    """A host lists these before it starts the server, so a stale one is a visible lie."""
    from mimem.assistant import server

    declared = {tool["name"] for tool in manifest["tools"]}
    actual = {
        name
        for name in dir(server)
        if callable(getattr(server, name, None)) and not name.startswith("_")
    }
    assert declared <= actual, f"declared but missing: {sorted(declared - actual)}"


def test_building_produces_an_installable_zip() -> None:
    """The check the plan's risk table asked for: that the bundle can still be produced."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "build_extension", ROOT / "packaging" / "build_extension.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.check(json.loads(MANIFEST.read_text(encoding="utf-8"))) == []
    out = module.build()
    assert out.exists()
    with zipfile.ZipFile(out) as bundle:
        names = bundle.namelist()
        assert "manifest.json" in names
        assert bundle.testzip() is None
    assert json.loads(zipfile.ZipFile(out).read("manifest.json"))["name"] == "mimem"
