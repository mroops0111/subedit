import typing

from ..domain.models.diagnostic import RuleMetadata
from ..domain.ports.rule import Rule


HEADING = '# Rules'
PREAMBLE = (
    'Generated from `RuleMetadata`. Edit the rule, not this file.\n\n'
    'The fix kind states who resolves a finding. A mechanical kind is repaired without telling the author, '
    'so only a rewrite reaches an agent.\n\n'
    'The level says whether a rewrite blocks. An error fails check and stops an agent, '
    'while a warning is shown as advice. Set either per rule under `[rules]`, '
    'and the Vale rules the same way by name, as in `"subedit.DateRef" = "off"`.'
)


def render(rules: tuple[Rule[typing.Any], ...]) -> str:
    sorted_rules = sorted(rules, key=lambda rule: (rule.metadata.fix_kind.value, rule.metadata.rule_id))
    lines = [HEADING, '', PREAMBLE, '', '| Rule | Fix kind | Level | Summary |', '| --- | --- | --- | --- |']
    lines.extend(_row(rule.metadata) for rule in sorted_rules)
    return '\n'.join(lines) + '\n'


def _row(metadata: RuleMetadata) -> str:
    return f'| `{metadata.rule_id}` | {metadata.fix_kind.value} | {metadata.default_severity.name.lower()} | {metadata.summary} |'
