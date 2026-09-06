"""The linter: the acceptance test for the whole pipeline."""

from mimem.lint.artefact_rules import ARTEFACT_RULE_TYPES, ArtefactRule, Bundle, artefact_rules
from mimem.lint.rules import DEFAULT_RULES, LintRule, Severity, Violation
from mimem.lint.runner import LintReport, lint, lint_all, lint_script
from mimem.lint.script_rules import SCRIPT_RULE_TYPES, ScriptRule, script_rules

__all__ = [
    "ARTEFACT_RULE_TYPES",
    "DEFAULT_RULES",
    "SCRIPT_RULE_TYPES",
    "ArtefactRule",
    "Bundle",
    "LintReport",
    "LintRule",
    "ScriptRule",
    "Severity",
    "Violation",
    "artefact_rules",
    "lint",
    "lint_all",
    "lint_script",
    "script_rules",
]
