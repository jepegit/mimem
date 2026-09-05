"""Run the lint rules and summarise the result.

Two entry points, because there are two kinds of rule. :func:`lint` reads narration text and is
what ``mimem narrate`` uses; :func:`lint_script` reads the plan as well, and is the real
acceptance test -- it runs the text rules over the rendered audio *and* the structural rules over
the script, so one report covers "would this be unspeakable" and "would this be unmemorable".
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from mimem.config import Profile
from mimem.ir import Script
from mimem.lint.rules import DEFAULT_RULES, LintRule, Severity, Violation
from mimem.lint.script_rules import ScriptRule, script_rules


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
    _sort(report)
    return report


def lint_script(
    script: Script,
    audio: str | None = None,
    profile: Profile | None = None,
    rules: tuple[ScriptRule, ...] | None = None,
) -> LintReport:
    """Check a plan, and the narration it renders to, against the design rules."""
    from mimem.render import render_audio

    structural = rules if rules is not None else script_rules(profile)
    report = LintReport(checked_rules=[r.id for r in structural])
    for rule in structural:
        report.violations.extend(rule.check(script))

    text_report = lint(audio if audio is not None else render_audio(script))
    report.violations.extend(text_report.violations)
    report.checked_rules.extend(text_report.checked_rules)
    _sort(report)
    return report


def _sort(report: LintReport) -> None:
    report.violations.sort(key=lambda v: (v.severity is Severity.WARNING, v.rule, v.line or 0))
