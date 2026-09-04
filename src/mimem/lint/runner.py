"""Run the lint rules and summarise the result."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from mimem.lint.rules import DEFAULT_RULES, LintRule, Severity, Violation


@dataclass
class LintReport:
    violations: list[Violation] = field(default_factory=list)
    checked_rules: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[Violation]:
        return [v for v in self.violations if v.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Violation]:
        return [v for v in self.violations if v.severity is Severity.WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def counts(self) -> Counter[str]:
        return Counter(v.rule for v in self.violations)

    def summary(self) -> str:
        if not self.violations:
            return f"clean: {len(self.checked_rules)} rules, no violations"
        parts = [f"{rule} x{n}" for rule, n in self.counts().most_common()]
        return f"{len(self.errors)} error(s), {len(self.warnings)} warning(s): {', '.join(parts)}"


def lint(text: str, rules: tuple[LintRule, ...] = DEFAULT_RULES) -> LintReport:
    """Check narration text against the design rules."""
    report = LintReport(checked_rules=[r.id for r in rules])
    for rule in rules:
        report.violations.extend(rule.check(text))
    report.violations.sort(key=lambda v: (v.severity is Severity.WARNING, v.line or 0))
    return report
