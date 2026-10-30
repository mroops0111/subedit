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
    # A broader surface comes first, since its rules read every narrower one,
    # and surfaces of one breadth keep the order their first rule takes.
    surfaces = list(dict.fromkeys(rule.surface for rule in rules))
    return sorted(surfaces, key=lambda surface: len(surface.__mro__))


def _row(metadata: RuleMetadata) -> str:
    return f'| `{metadata.rule_id}` | {metadata.fix_kind.value} | {metadata.default_severity.name.lower()} | {metadata.summary} |'
