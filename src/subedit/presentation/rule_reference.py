import typing

from ..domain.models.diagnostic import RuleMetadata
from ..domain.ports.rule import Rule
from ..domain.ports.source_parser import SourceParser


_HEADING = '# Rules'
_PREAMBLE = (
    'The fix kind states who resolves a finding. A mechanical kind is repaired without telling the author, '
    'so only a rewrite reaches an agent.\n\n'
    'The level says whether a rewrite blocks. An error fails check and stops an agent, '
    'while a warning is shown as advice. Set either per rule under `[rules]`, '
    'and the Vale rules the same way by name, as in `"subedit.DateRef" = "off"`.\n\n'
    'Surfaces names what each rule reads, as `[surfaces.<name>.rules]` names a surface to set the rule for it alone. '
    'docs/rules.md lists these with the bundled Vale style and AutoCorrect, and what each one catches.'
)


def render(rules: tuple[Rule[typing.Any], ...], parser: SourceParser[typing.Any]) -> str:
    """The native rules as one Markdown table, naming the surfaces each reads, those that read the most first."""
    surfaces = {id(rule): parser.surfaces_reading(rule.surface) for rule in rules}
    ordered = sorted(
        rules,
        key=lambda rule: (-len(surfaces[id(rule)]), rule.metadata.fix_kind.value, rule.metadata.rule_id),
    )
    lines = [
        _HEADING,
        '',
        _PREAMBLE,
        '',
        '| Rule | Surfaces | Fix kind | Level | Summary |',
        '| --- | --- | --- | --- | --- |',
    ]
    lines.extend(_row(rule.metadata, surfaces[id(rule)]) for rule in ordered)
    return '\n'.join(lines) + '\n'


def _row(metadata: RuleMetadata, surfaces: tuple[str, ...]) -> str:
    named = ', '.join(f'`{surface}`' for surface in surfaces) or 'None'
    return (
        f'| `{metadata.rule_id}` | {named} | {metadata.fix_kind.value} | '
        f'{metadata.default_severity.name.lower()} | {metadata.summary} |'
    )
