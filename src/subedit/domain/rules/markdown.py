import re
import typing

from ..models.diagnostic import Diagnostic, Fix, FixKind, RuleMetadata, Severity
from ..models.markdown import MarkdownBlock, MarkdownBlockKind
from ..models.title_case import title_case
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


HEADING_TITLE_CASE = RuleMetadata(
    rule_id='heading-title-case',
    summary='The English words of a Markdown heading are in Title Case.',
    fix_kind=FixKind.TARGETED,
)

MISSING_LEAD_SENTENCE = RuleMetadata(
    rule_id='missing-lead-sentence',
    summary='A heading opens with a sentence that frames its section, never straight into a list.',
    fix_kind=FixKind.REWRITE,
)

HEADING_NOT_NOUN_PHRASE = RuleMetadata(
    rule_id='heading-not-noun-phrase',
    summary='A Markdown heading is a noun phrase, not a question or an instruction.',
    fix_kind=FixKind.REWRITE,
    default_severity=Severity.WARNING,
)


_QUESTION_WORDS = frozenset({'when', 'what', 'where', 'why', 'how', 'who', 'which'})
# Verbs a heading most often opens with when it gives an instruction instead of naming its subject.
_IMPERATIVE_VERBS = frozenset(
    {
        'add',
        'apply',
        'avoid',
        'build',
        'check',
        'choose',
        'configure',
        'create',
        'define',
        'disable',
        'enable',
        'follow',
        'get',
        'install',
        'keep',
        'make',
        'open',
        'prefer',
        'read',
        'remove',
        'run',
        'set',
        'start',
        'stop',
        'update',
        'use',
        'write',
    }
)
_FIRST_WORD = re.compile(r'[A-Za-z]+')


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


class HeadingTitleCaseRule(Rule[MarkdownBlock]):
    metadata = HEADING_TITLE_CASE
    surface = MarkdownBlock

    def check(self, unit: MarkdownBlock, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if unit.kind is not MarkdownBlockKind.HEADING:
            return
        cased = title_case(unit.text, context.settings(self.metadata.rule_id).strings('keep'))
        if cased == unit.text:
            return
        yield Diagnostic(
            rule_id=self.metadata.rule_id,
            range=unit.range,
            message=(
                f'This heading is not in Title Case, so it reads "{cased}". '
                'List a name that stays lowercase, such as npm, under keep for this rule.'
            ),
            fix=Fix.targeted(unit.as_edit(cased)),
        )


class MissingLeadSentenceRule(Rule[MarkdownBlock]):
    metadata = MISSING_LEAD_SENTENCE
    surface = MarkdownBlock

    def check(self, unit: MarkdownBlock, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if not unit.leads_into_list:
            return
        yield Diagnostic(
            rule_id=self.metadata.rule_id,
            range=unit.range,
            message=(
                'This heading opens straight into a list. '
                'Add a sentence or two under it that frames what the list holds.'
            ),
            fix=Fix.rewrite(),
        )


class HeadingNotNounPhraseRule(Rule[MarkdownBlock]):
    metadata = HEADING_NOT_NOUN_PHRASE
    surface = MarkdownBlock

    def check(self, unit: MarkdownBlock, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if unit.kind is not MarkdownBlockKind.HEADING:
            return
        first_word = _FIRST_WORD.search(unit.text)
        word = first_word.group().lower() if first_word else ''
        if word in _QUESTION_WORDS or unit.text.rstrip().endswith('?'):
            shape = 'a question'
        elif word in _IMPERATIVE_VERBS:
            shape = 'an instruction'
        else:
            return
        yield Diagnostic(
            rule_id=self.metadata.rule_id,
            range=unit.range,
            message=(
                f'This heading reads as {shape}. '
                'Name the subject of the section as a noun phrase, such as Installation rather than How to Install.'
            ),
            fix=Fix.rewrite(),
        )
