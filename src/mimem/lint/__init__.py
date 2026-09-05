"""The linter: the acceptance test for the whole pipeline."""

from mimem.lint.rules import DEFAULT_RULES, LintRule, Severity, Violation
from mimem.lint.runner import LintReport, lint, lint_script
from mimem.lint.script_rules import SCRIPT_RULE_TYPES, ScriptRule, script_rules

__all__ = [
    "DEFAULT_RULES",
    "SCRIPT_RULE_TYPES",
    "LintReport",
    "LintRule",
    "ScriptRule",
    "Severity",
    "Violation",
    "lint",
    "lint_script",
    "script_rules",
]
