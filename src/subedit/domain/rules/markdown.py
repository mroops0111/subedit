import re
import typing

from ..models.diagnostic import Diagnostic, Fix, FixKind, RuleMetadata
from ..models.markdown import MarkdownBlock, MarkdownBlockKind
from ..ports.rule import Rule, RuleContext


PARAGRAPH_LINE_BREAK = RuleMetadata(
    rule_id='paragraph-line-break',
    summary=(
        'A Markdown paragraph stays on one source line, since a renderer or a synced copy '
        'may show every newline as a break.'
    ),
    fix_kind=FixKind.REFLOW,
)

HEADING_WRAPPED_IN_BOLD = RuleMetadata(
    rule_id='heading-wrapped-in-bold',
    summary='A Markdown heading is not wrapped in bold, since a heading already renders bold.',
    fix_kind=FixKind.TARGETED,
)


# The whole heading sits inside one pair of markers, with no second pair closing and reopening in between.
_WHOLLY_BOLD = re.compile(r'^(\*\*|__)(?P<inner>(?:(?!\1).)+)\1$')


class ParagraphLineBreakRule(Rule[MarkdownBlock]):
    metadata = PARAGRAPH_LINE_BREAK
    surface = MarkdownBlock

    def check(self, unit: MarkdownBlock, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if unit.kind is not MarkdownBlockKind.PARAGRAPH or not unit.soft_break_count:
            return
        yield Diagnostic(
            rule_id=self.metadata.rule_id,
            range=unit.range,
            message=(
                'This paragraph is broken across source lines. '
                'Markdown has no line width, and GitHub, Notion, and Heptabase may show each newline as a break, '
                'so a paragraph takes one line. End a line with two spaces or a backslash where a break is meant.'
            ),
            fix=Fix.reflow(unit.as_edit(unit.joined())),
        )


class HeadingWrappedInBoldRule(Rule[MarkdownBlock]):
    metadata = HEADING_WRAPPED_IN_BOLD
    surface = MarkdownBlock

    def check(self, unit: MarkdownBlock, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if unit.kind is not MarkdownBlockKind.HEADING:
            return
        wholly_bold = _WHOLLY_BOLD.match(unit.text.strip())
        if wholly_bold is None:
            return
        yield Diagnostic(
            rule_id=self.metadata.rule_id,
            range=unit.range,
            message='This heading is wrapped in bold, which a heading already renders as, so the markers go.',
            fix=Fix.targeted(unit.as_edit(wholly_bold.group('inner').strip())),
        )
