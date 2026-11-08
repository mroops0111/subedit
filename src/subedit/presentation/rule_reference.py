import typing

from ..domain.models import ProseUnit
from ..domain.models.diagnostic import RuleMetadata
from ..domain.ports.rule import Rule


_HEADING = '# Rules'
_PREAMBLE = (
    'The fix kind states who resolves a finding. A mechanical kind is repaired without telling the author, '
    'so only a rewrite reaches an agent.\n\n'
    'The level says whether a rewrite blocks. An error fails check and stops an agent, '
    'while a warning is shown as advice. Set either per rule under `[rules]`, '
    'and the Vale rules the same way by name, as in `"subedit.DateRef" = "off"`.\n\n'
    'Each section names the surface its rules read. '
    'docs/rules.md lists these with the bundled Vale style and AutoCorrect, and what each one catches.'
)


def render(rules: tuple[Rule[typing.Any], ...]) -> str:
    """The native rules as Markdown, one section per surface."""
    lines = [_HEADING, '', _PREAMBLE]
    for surface in _surfaces(rules):
        section = sorted(
            (rule for rule in rules if rule.surface is surface),
            key=lambda rule: (rule.metadata.fix_kind.value, rule.metadata.rule_id),
        )
        lines.extend(
            ['', f'## {surface.surface_name}', '', '| Rule | Fix kind | Level | Summary |', '| --- | --- | --- | --- |']
        )
        lines.extend(_row(rule.metadata) for rule in section)
    return '\n'.join(lines) + '\n'


def _surfaces(rules: tuple[Rule[typing.Any], ...]) -> list[type[ProseUnit]]:
    # A broader surface comes before every narrower one, since its rules read them too,
    # and otherwise each keeps the order its first rule takes.
    pending = list(dict.fromkeys(rule.surface for rule in rules))
    ordered: list[type[ProseUnit]] = []
    while pending:
        ready = next(
            surface
            for surface in pending
            if not any(other is not surface and issubclass(surface, other) for other in pending)
        )
        ordered.append(ready)
        pending.remove(ready)
    return ordered


def _row(metadata: RuleMetadata) -> str:
    return f'| `{metadata.rule_id}` | {metadata.fix_kind.value} | {metadata.default_severity.name.lower()} | {metadata.summary} |'
