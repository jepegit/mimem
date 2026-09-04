from __future__ import annotations

from pathlib import Path

from mimem.clean import clean
from mimem.ingest import load
from mimem.ir import BlockKind, BlockRole


def test_markdown_structure(markdown_file: Path) -> None:
    doc = load(markdown_file)
    kinds = [b.kind for b in doc.blocks]
    assert kinds[0] is BlockKind.HEADING
    assert doc.blocks[0].level == 1
    assert BlockKind.LIST_ITEM in kinds
    assert doc.source.title == "On Interphase Repair"


def test_markdown_paragraph_lines_are_joined(markdown_file: Path) -> None:
    doc = clean(load(markdown_file))
    para = next(b for b in doc.blocks if b.text.startswith("Some background"))
    assert "\n" not in para.text
    assert para.text.endswith("one paragraph.")


def test_markdown_sections_are_roled(markdown_file: Path) -> None:
    doc = clean(load(markdown_file))
    methods = [b for b in doc.blocks if b.role is BlockRole.METHODS]
    assert methods and methods[0].text == "2. Methods"


def test_plain_text_file(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("One paragraph here.\n\nAnd a second one.\n", encoding="utf-8")
    doc = clean(load(path))
    assert len(doc.blocks) == 2
    assert doc.blocks[1].sentence_texts() == ["And a second one."]


def test_code_fences_are_kept_verbatim(tmp_path: Path) -> None:
    path = tmp_path / "b.md"
    path.write_text("Intro line.\n\n```python\nx = 1\ny = 2\n```\n", encoding="utf-8")
    doc = clean(load(path))
    code = [b for b in doc.blocks if b.kind is BlockKind.CODE]
    assert len(code) == 1
    assert "x = 1\ny = 2" in code[0].text  # line structure preserved
