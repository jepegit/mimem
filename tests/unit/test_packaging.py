"""The extension bundle: the only way into Claude Desktop, so it has to keep building.

This is not a test of zip files. It is a test of the two ways the bundle goes wrong quietly:
the manifest drifts from what a host will accept, and the version drifts from the package's,
so someone installs "0.1.0" and gets whatever is on main.

The bundle is a manifest and an icon; the server it launches is fetched by ``uv`` at first start,
for the user's own platform. That is why there is no dependency matrix to test here — and why
there is a test that the launch command has not quietly become something else.
"""

from __future__ import annotations

import asyncio
import json
import zipfile
from pathlib import Path

import pytest

from mimem.assistant.workspace import WORKSPACE_ENV

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "packaging" / "manifest.json"
REPO = "https://github.com/jepegit/mimem"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _registered(listing: str) -> set[str]:
    """The names the running server actually answers with, via the SDK's own registry."""
    from mimem.assistant import server

    return {item.name for item in asyncio.run(getattr(server.mcp, listing)())}


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
    assert f"git+{REPO}@v{manifest['version']}" in config["args"]


def test_the_launch_command_is_pinned_to_this_version(manifest: dict) -> None:
    """An unpinned ``--from`` resolves to whatever is on main at first start.

    Which means a bundle labelled 0.1.0, downloaded from the 0.1.0 release, installs code that
    was written after it -- and the version the user is shown is then a number with nothing
    behind it. The tag in the ref is asserted against the manifest version rather than merely
    being present, so a release that forgets to move it fails here instead of silently
    shipping the previous version's code.
    """
    ref = next(arg for arg in manifest["server"]["mcp_config"]["args"] if arg.startswith("git+"))
    assert ref.endswith(f"@v{manifest['version']}"), f"{ref} is not pinned to this version"


def test_the_settings_form_covers_what_the_server_reads(manifest: dict) -> None:
    """The point of a manifest over hand-edited JSON: the user gets a form, not a variable."""
    env = manifest["server"]["mcp_config"]["env"]
    assert WORKSPACE_ENV in env
    for placeholder in env.values():
        key = placeholder.removeprefix("${user_config.").removesuffix("}")
        assert key in manifest["user_config"], f"{placeholder} has no user_config entry"


def test_the_declared_tools_are_exactly_the_registered_ones(manifest: dict) -> None:
    """A host lists these before it starts the server, so a stale one is a visible lie.

    This assertion used to be ``declared <= actual`` against every public callable in the
    module, which is two weaknesses at once. It could not see a tool the server registers and
    the manifest omits -- and that is the direction the drift actually went: ``next_figure``
    shipped registered and undeclared, so the install screen offered ten tools and the server
    answered eleven. Comparing against ``dir(server)`` was the reason the looser direction was
    chosen, because that set also contains the prompts and every helper. Asking the registry
    costs one ``list_tools`` call and makes equality the natural thing to assert.
    """
    declared = {tool["name"] for tool in manifest["tools"]}
    assert declared == _registered("list_tools")


def test_the_declared_prompts_are_exactly_the_registered_ones(manifest: dict) -> None:
    """Prompts appear in the host's own menu, and drift the same way tools do."""
    declared = {prompt["name"] for prompt in manifest["prompts"]}
    assert declared == _registered("list_prompts")


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
