import dataclasses
import pathlib
import typing

import pytest

from subedit.application import Fixer, Linter, RuleEngine
from subedit.domain import (
    CommentGroup,
    Diagnostic,
    Document,
    FileType,
    Fix,
    FixKind,
    ParsedDocument,
    Prose,
    ProseLine,
    ProseUnit,
    Rule,
    RuleContext,
    RuleMetadata,
    RuleSet,
    SourceParser,
    SourceRange,
    TextEdit,
)
from subedit.infrastructure import ALL_RULES, COMMENT_PARSER, CompositeParser, MarkdownParser
from subedit.presentation import rule_reference


@dataclasses.dataclass(frozen=True, slots=True)
class Subtitle(ProseUnit):
    """One cue of a subtitle file, a surface subedit does not ship."""

    surface_name: typing.ClassVar[str] = 'Subtitles'

    range: SourceRange
    text: str

    def prose(self) -> Prose:
        return Prose(self.text)

    def prose_lines(self) -> tuple[ProseLine, ...]:
        return (ProseLine(self.range, self.text, ends_paragraph=True, opens_paragraph=True),)

    def editable_ranges(self) -> tuple[SourceRange, ...]:
        return (self.range,)

    def code_ranges(self) -> tuple[SourceRange, ...]:
        return ()


class SubtitleParser(SourceParser[Subtitle]):
    @property
    def file_types(self) -> tuple[FileType, ...]:
        return (FileType('subtitle', frozenset({'.srt'}), '.srt'),)

    def read(self, document: Document) -> ParsedDocument[Subtitle]:
        cues: list[Subtitle] = []
        offset = 0
        for line in document.text.split('\n'):
            if line and not line[0].isdigit():
                cues.append(Subtitle(SourceRange(offset, offset + len(line.encode('utf-8'))), line))
            offset += len(line.encode('utf-8')) + 1
        return ParsedDocument(tuple(cues))


class ShoutingCueRule(Rule[Subtitle]):
    metadata = RuleMetadata(rule_id='shouting-cue', summary='A cue is not all capitals.', fix_kind=FixKind.TARGETED)
    surface = Subtitle

    def check(self, unit: Subtitle, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if unit.text.isupper():
            yield Diagnostic(
                rule_id=self.metadata.rule_id,
                range=unit.range,
                message='This cue shouts.',
                fix=Fix.targeted(TextEdit(unit.range, unit.text.capitalize())),
            )


class SeenUnitsRule(Rule[CommentGroup]):
    metadata = RuleMetadata(rule_id='seen-comments', summary='Records what it reads.', fix_kind=FixKind.REWRITE)
    surface = CommentGroup

    def __init__(self) -> None:
        self.seen: list[ProseUnit] = []

    def check(self, unit: CommentGroup, context: RuleContext) -> typing.Iterable[Diagnostic]:
        self.seen.append(unit)
        return ()


# A surface subedit does not ship plugs in as a unit, a parser,
# and rules, with no change to the linter, fixer, or engine.
PARSER = CompositeParser((COMMENT_PARSER, MarkdownParser(), SubtitleParser()))


def rule_set(*rules: Rule[typing.Any]) -> RuleSet:
    return RuleSet(enabled_rule_ids=frozenset(rule.metadata.rule_id for rule in rules))


def subtitles(text: str) -> Document:
    return Document(uri='file:///film.srt', text=text, language_id='subtitle')


def test_the_new_surface_is_found_by_its_extension() -> None:
    assert PARSER.language_id_for(pathlib.Path('film.srt').suffix) == 'subtitle'
    assert PARSER.language_id_for('.md') == 'markdown'
    assert PARSER.language_id_for('.py') == 'python'


def test_the_new_surface_is_fixed_by_the_unchanged_fixer() -> None:
    rules = (*ALL_RULES, ShoutingCueRule())
    result = Fixer(Linter(PARSER, RuleEngine(rules))).run(subtitles('1\nGET DOWN\n2\nquiet now\n'), rule_set(*rules))
    assert result.document.text == '1\nGet down\n2\nquiet now\n'


def test_a_rule_of_another_surface_never_reads_the_new_one() -> None:
    comment_rule = SeenUnitsRule()
    Linter(PARSER, RuleEngine((comment_rule, ShoutingCueRule()))).run(
        subtitles('1\nGET DOWN\n'), rule_set(comment_rule, ShoutingCueRule())
    )
    assert comment_rule.seen == []


def test_the_new_rule_never_reads_comments() -> None:
    document = Document(uri='file:///a.py', text='# LOUD COMMENT\nx = 1\n', language_id='python')
    report = Linter(PARSER, RuleEngine((ShoutingCueRule(),))).run(document, rule_set(ShoutingCueRule()))
    assert report.is_clean


def test_the_rule_reference_gives_the_new_surface_its_own_section() -> None:
    reference = rule_reference.render((*ALL_RULES, ShoutingCueRule()))
    section = reference.split('## Subtitles\n', 1)[1]
    assert '`shouting-cue`' in section
    assert '## ' not in section, 'the new surface is no broader than comments or Markdown, so its section comes last'


def test_every_shipped_surface_names_itself() -> None:
    surfaces = {rule.surface for rule in ALL_RULES} - {ProseUnit}
    unnamed = [surface.__name__ for surface in surfaces if 'surface_name' not in vars(surface)]
    assert not unnamed, f'surfaces that would borrow the name of every surface: {unnamed}'


def test_two_parsers_may_not_claim_one_language() -> None:
    with pytest.raises(ValueError, match='same language'):
        CompositeParser((MarkdownParser(), MarkdownParser()))
