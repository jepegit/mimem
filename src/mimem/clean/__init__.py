"""Stage 2: corpus-level cleanup, shared by every source format."""

from mimem.clean.artifacts import strip_page_artifacts
from mimem.clean.dehyphenate import dehyphenate, dehyphenate_text
from mimem.clean.line_numbers import strip_line_numbers
from mimem.clean.merge import merge_continuations
from mimem.clean.pipeline import clean
from mimem.clean.sections import assign_sections, role_for_heading
from mimem.clean.sentences import sentence_spans, split_sentences

__all__ = [
    "assign_sections",
    "clean",
    "dehyphenate",
    "dehyphenate_text",
    "merge_continuations",
    "role_for_heading",
    "sentence_spans",
    "split_sentences",
    "strip_line_numbers",
    "strip_page_artifacts",
]
