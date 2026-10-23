import pytest

from subedit.application import Linter, RuleEngine
from subedit.domain import (
    CommentGroup,
    Diagnostic,
    Document,
    FileType,
    Fix,
    FixKind,
    ParsedDocument,
    Rule,
    RuleContext,
    RuleMetadata,
    RuleSet,
    RuleSettings,
    Severity,
    SourceParser,
    SourceRange,
    TextEdit,
)
from subedit.infrastructure import COMMENT_PARSER, DEFAULT_PARSER


class RecordingRule(Rule[CommentGroup]):
    surface = CommentGroup

    def __init__(self, rule_id: str, fix_kind: FixKind = FixKind.REWRITE) -> None:
        self.metadata = RuleMetadata(rule_id=rule_id, summary='test rule', fix_kind=fix_kind)
        self.seen: list[str] = []

    def check(self, group: CommentGroup, context: RuleContext):
        self.seen.append(group.prose().flattened)
        yield Diagnostic(
            rule_id=self.metadata.rule_id,
            range=group.range,
            message=f'{self.metadata.rule_id} at width {context.rule_set.line_width}',
        )


class SilentRule(Rule[CommentGroup]):
    surface = CommentGroup
    metadata = RuleMetadata(rule_id='silent', summary='never fires', fix_kind=FixKind.REWRITE)

    def check(self, group: CommentGroup, context: RuleContext):
        return ()


def document(source: str) -> Document:
    return Document(uri='file:///a.py', text=source, language_id='python')


def rule_set(*ids: str, **kwargs: object) -> RuleSet:
    return RuleSet(enabled_rule_ids=frozenset(ids), **kwargs)  # pyright: ignore[reportArgumentType]


def test_duplicate_rule_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match='Duplicate rule ids'):
        RuleEngine((RecordingRule('same'), RecordingRule('same')))


def test_a_new_rule_needs_no_engine_change() -> None:
    rule = RecordingRule('brand-new')
    engine = RuleEngine((rule,))

    report = Linter(DEFAULT_PARSER, engine).run(document('# a note\n'), rule_set('brand-new'))
    assert [item.rule_id for item in report.diagnostics] == ['brand-new']
    assert rule.seen == ['a note']


def test_a_disabled_rule_does_not_run() -> None:
    rule = RecordingRule('off')
    Linter(DEFAULT_PARSER, RuleEngine((rule,))).run(document('# a note\n'), rule_set())
    assert rule.seen == []


def test_every_block_reaches_every_enabled_rule() -> None:
    first, second = RecordingRule('first'), RecordingRule('second')
    engine = RuleEngine((first, second))
    Linter(DEFAULT_PARSER, engine).run(document('# one\nx = 1\n# two\n'), rule_set('first', 'second'))
    assert first.seen == ['one', 'two']
    assert second.seen == ['one', 'two']


def test_severity_comes_from_configuration_when_set() -> None:
    engine = RuleEngine((RecordingRule('tunable'),))
    rules = rule_set('tunable', settings={'tunable': RuleSettings(severity=Severity.WARNING)})
    report = Linter(DEFAULT_PARSER, engine).run(document('# note\n'), rules)
    assert report.diagnostics[0].severity is Severity.WARNING


def test_severity_falls_back_to_the_rule_default() -> None:
    engine = RuleEngine((RecordingRule('plain'),))
    report = Linter(DEFAULT_PARSER, engine).run(document('# note\n'), rule_set('plain'))
    assert report.diagnostics[0].severity is Severity.ERROR


def test_line_width_reaches_the_rule_through_the_context() -> None:
    engine = RuleEngine((RecordingRule('widthy'),))
    report = Linter(DEFAULT_PARSER, engine).run(document('# note\n'), rule_set('widthy', line_width=88))
    assert 'width 88' in report.diagnostics[0].message


def test_an_unsupported_language_produces_an_empty_report() -> None:
    engine = RuleEngine((RecordingRule('any'),))
    unsupported = Document(uri='a.rb', text='# note', language_id='ruby')
    assert Linter(DEFAULT_PARSER, engine).run(unsupported, rule_set('any')).is_clean


def test_a_rule_that_never_fires_produces_a_clean_report() -> None:
    engine = RuleEngine((SilentRule(),))
    assert Linter(DEFAULT_PARSER, engine).run(document('# note\n'), rule_set('silent')).is_clean


def test_diagnostics_come_back_in_source_order() -> None:
    engine = RuleEngine((RecordingRule('a'), RecordingRule('b')))
    report = Linter(DEFAULT_PARSER, engine).run(document('# one\nx = 1\n# two\n'), rule_set('a', 'b'))
    starts = [item.range.start for item in report.diagnostics]
    assert starts == sorted(starts)


def test_rule_settings_read_integer_options_defensively() -> None:
    settings = RuleSettings(options={'width': 90, 'flag': True, 'name': 'x'})
    assert settings.integer('width', 120) == 90
    assert settings.integer('flag', 120) == 120
    assert settings.integer('name', 120) == 120
    assert settings.integer('missing', 120) == 120


def test_a_fix_kind_survives_the_engine() -> None:
    class FixingRule(Rule[CommentGroup]):
        surface = CommentGroup
        metadata = RuleMetadata(rule_id='fixer', summary='fixes', fix_kind=FixKind.TARGETED)

        def check(self, group: CommentGroup, context: RuleContext):
            edit = TextEdit(SourceRange(group.range.start, group.range.start), '!')
            yield Diagnostic(
                rule_id='fixer',
                range=group.range,
                message='fix me',
                fix=Fix.targeted(edit),
            )

    engine = RuleEngine((FixingRule(),))
    report = Linter(DEFAULT_PARSER, engine).run(document('# note\n'), rule_set('fixer'))
    assert report.mechanical and report.mechanical[0].fix is not None
    assert report.mechanical[0].fix.kind is FixKind.TARGETED


def test_one_inspection_parses_the_document_once() -> None:
    class CountingParser(SourceParser[CommentGroup]):
        def __init__(self) -> None:
            self.parse_count = 0

        @property
        def file_types(self) -> tuple[FileType, ...]:
            return COMMENT_PARSER.file_types

        def read(self, document: Document) -> ParsedDocument[CommentGroup]:
            self.parse_count += 1
            return COMMENT_PARSER.read(document)

    parser = CountingParser()
    document = Document(uri='file:///a.py', text='x = 1  # a note\n# a line\ny = 2\n', language_id='python')
    inspection = Linter(parser, RuleEngine(())).inspect(document, RuleSet(enabled_rule_ids=frozenset()))
    assert parser.parse_count == 1
    assert len(inspection.prose_map.editable) == 1, 'the trailing note shares its line with code'
