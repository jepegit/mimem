"""Run the lint rules and summarise the result.

Three entry points, because there are three kinds of rule. :func:`lint` reads narration text and
is what ``mimem narrate`` uses. :func:`lint_script` reads the plan as well, so one report covers
"would this be unspeakable" and "would this be unmemorable". :func:`lint_all` adds the source
document and the written track, and is the real acceptance test -- only it can check that the
*differences between the artefacts* are the ones the design asks for.

A report always names the rules it did not run. ``lint_script`` cannot check ``NUM-06``, because
``NUM-06`` is a statement about two files and it has one; the report says so rather than
counting to a smaller number and calling it clean.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from mimem.config import Profile
from mimem.ir import Script
from mimem.lint.artefact_rules import Bundle, artefact_rules
from mimem.lint.rules import DEFAULT_RULES, LintRule, Severity, Violation
from mimem.lint.script_rules import ScriptRule, script_rules


@dataclass
class LintReport:
    violations: list[Violation] = field(default_factory=list)
    checked_rules: list[str] = field(default_factory=list)
    #: Rules this run could not check, and why. Empty for a full build.
    skipped: list[str] = field(default_factory=list)

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
        tail = f" ({len(self.skipped)} not checked here)" if self.skipped else ""
        if not self.violations:
            return f"clean: {len(self.checked_rules)} rules, no violations{tail}"
        parts = [f"{rule} x{n}" for rule, n in self.counts().most_common()]
        return (
            f"{len(self.errors)} error(s), {len(self.warnings)} warning(s): "
            f"{', '.join(parts)}{tail}"
        )


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
    report.skipped = [
        f"{rule.id}: needs the source document and the written track" for rule in artefact_rules()
    ]
    _sort(report)
    return report


def lint_all(bundle: Bundle, profile: Profile | None = None) -> LintReport:
    """Every rule there is: the plan, the narration, and the differences between the artefacts.

    This is what ``mimem build`` runs and what CI enforces. Nothing is skipped, so ``clean``
    from here means clean.
    """
    report = lint_script(bundle.script, bundle.audio, profile)
    report.skipped = []
    for rule in artefact_rules(profile):
        report.violations.extend(rule.check(bundle))
        report.checked_rules.append(rule.id)
    _sort(report)
    return report


def _sort(report: LintReport) -> None:
    report.violations.sort(key=lambda v: (v.severity is Severity.WARNING, v.rule, v.line or 0))
