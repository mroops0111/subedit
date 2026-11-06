import re
import typing

from ..models.diagnostic import Diagnostic, Fix, FixKind, RuleMetadata
from ..models.markdown import MarkdownBlock, MarkdownBlockKind
from ..models.rule_option import HEADING_LEVELS, ChoiceOption, HeadingLevelsOption, WordsOption
from ..models.rule_set import RuleSettings
from ..models.title_case import TITLE_CASE_STYLES, TitleCaseStyle, capitalized_ambiguous_words, title_case
from ..models.word_classes import (
    ARTICLES,
    COORDINATING_CONJUNCTIONS,
    OBJECT_OPENERS,
    PREPOSITIONS,
    QUESTION_WORDS,
    SUBORDINATING_CONJUNCTIONS,
)
from ..ports.rule import Rule, RuleContext


_WORD = re.compile(r'[A-Za-z]+')
# A word that cannot give an instruction even when an object opener follows it, as in For a Client or All the Rules.
_NOT_VERBS = (
    ARTICLES | COORDINATING_CONJUNCTIONS | SUBORDINATING_CONJUNCTIONS | PREPOSITIONS | OBJECT_OPENERS | QUESTION_WORDS
)
# The heading levels a heading rule reads, all of them unless the project narrows it, such as to leave out a title.
LEVELS = HeadingLevelsOption('levels', tuple(HEADING_LEVELS))


# The whole heading sits inside one pair of markers, with no second pair closing and reopening in between.
_WHOLLY_BOLD = re.compile(r'^(\*\*|__)(?P<inner>(?:(?!\1).)+)\1$')


class ParagraphLineBreakRule(Rule[MarkdownBlock]):
    metadata = RuleMetadata(
        rule_id='paragraph-line-break',
        summary=(
            'A Markdown paragraph stays on one source line, since a renderer or a synced copy '
            'may show every newline as a break.'
        ),
        fix_kind=FixKind.REFLOW,
    )
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
    metadata = RuleMetadata(
        rule_id='heading-wrapped-in-bold',
        summary='A Markdown heading is not wrapped in bold, since a heading already renders bold.',
        fix_kind=FixKind.TARGETED,
    )
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


# Names that stay lowercase in a title, such as npm, which list labels follow too.
EXCEPTIONS = WordsOption('exceptions', ())
# The standard that decides which words stay lowercase in a title, which list labels follow too.
STYLE = ChoiceOption('style', 'apa', choices=tuple(TITLE_CASE_STYLES))


class HeadingTitleCaseRule(Rule[MarkdownBlock]):
    metadata = RuleMetadata(
        rule_id='heading-title-case',
        summary='The English words of a Markdown heading are in Title Case.',
        fix_kind=FixKind.TARGETED,
        options=(EXCEPTIONS, STYLE, LEVELS),
    )
    surface = MarkdownBlock

    def check(self, unit: MarkdownBlock, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if not _is_listed_heading(unit, context.settings(self.metadata.rule_id)):
            return
        yield from _title_case_findings(self.metadata.rule_id, unit, context, 'heading')


class TableHeaderTitleCaseRule(Rule[MarkdownBlock]):
    metadata = RuleMetadata(
        rule_id='table-header-title-case',
        summary='The English words of a Markdown table header are in Title Case.',
        fix_kind=FixKind.TARGETED,
    )
    surface = MarkdownBlock

    def check(self, unit: MarkdownBlock, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if unit.kind is not MarkdownBlockKind.TABLE_HEADER:
            return
        yield from _title_case_findings(self.metadata.rule_id, unit, context, 'table header')


def _title_case_findings(
    rule_id: str, unit: MarkdownBlock, context: RuleContext, what: str
) -> typing.Iterator[Diagnostic]:
    exceptions, style = title_case_settings(context)
    cased = title_case(unit.text, exceptions, style)
    if cased != unit.text:
        yield Diagnostic(
            rule_id=rule_id,
            range=unit.range,
            message=(
                f'This {what} is not in Title Case, so it reads "{cased}". '
                'List a name that stays lowercase, such as npm, under exceptions for heading-title-case.'
            ),
            fix=Fix.targeted(unit.as_edit(cased)),
        )
    ambiguous = capitalized_ambiguous_words(cased, style)
    if ambiguous:
        yield Diagnostic(
            rule_id=rule_id,
            range=unit.range,
            message=(
                f'{", ".join(ambiguous)} stays lowercase in Title Case as a preposition or conjunction, '
                'as in Getting Started in Go, but is capitalized as an adverb, as in Set Up. '
                'Lowercase it unless it is an adverb here.'
            ),
            fix=Fix.rewrite(),
            # Whether the word is a preposition or an adverb is a matter of syntax, which subedit can only guess.
            tentative=True,
        )


def title_case_settings(context: RuleContext) -> tuple[tuple[str, ...], TitleCaseStyle]:
    """The exceptions and the standard the heading rule sets, which every title follows, so no two disagree."""
    settings = context.settings(HeadingTitleCaseRule.metadata.rule_id)
    return settings.value(EXCEPTIONS), TITLE_CASE_STYLES[settings.value(STYLE)]


class MissingLeadSentenceRule(Rule[MarkdownBlock]):
    metadata = RuleMetadata(
        rule_id='missing-lead-sentence',
        summary='A heading opens with a sentence that frames its section, never straight into a list.',
        fix_kind=FixKind.REWRITE,
    )
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
    metadata = RuleMetadata(
        rule_id='heading-not-noun-phrase',
        summary='A Markdown heading is a noun phrase, not a question or an instruction.',
        fix_kind=FixKind.REWRITE,
        options=(LEVELS,),
    )
    surface = MarkdownBlock

    def check(self, unit: MarkdownBlock, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if not _is_listed_heading(unit, context.settings(self.metadata.rule_id)):
            return
        words = list(_WORD.finditer(unit.text))
        opens_with_question_word = bool(words) and words[0].group().lower() in QUESTION_WORDS
        if opens_with_question_word or unit.text.rstrip().endswith(('?', '\uff1f')):
            shape, is_sure = 'a question', True
        elif _opens_with_verb_and_object(unit.text, words):
            shape, is_sure = 'an instruction', False
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
            # A word opening an object marks the word before it as a verb, which only syntax could confirm.
            tentative=not is_sure,
        )


# An instruction is a verb and its object, so a first word followed straight by an object opener,
# as in Add a Rule, reads as one, while a noun phrase such as Build Steps has none.
def _opens_with_verb_and_object(text: str, words: list[re.Match[str]]) -> bool:
    if len(words) < 2:
        return False
    first, second = words[0], words[1]
    verb = first.group().lower()
    if verb in _NOT_VERBS or _is_gerund(verb) or text[first.end() : second.start()].strip():
        return False
    return second.group().lower() in OBJECT_OPENERS


# A gerund such as Using names an activity, while Bring or String, whose stem before ing holds no vowel, is a verb.
def _is_gerund(word: str) -> bool:
    return word.endswith('ing') and any(letter in 'aeiouy' for letter in word[:-3])


def _is_listed_heading(unit: MarkdownBlock, settings: RuleSettings) -> bool:
    return unit.kind is MarkdownBlockKind.HEADING and unit.level in settings.value(LEVELS)
