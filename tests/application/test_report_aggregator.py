import dataclasses
import importlib.machinery
import importlib.util
import pathlib
import shutil

import pytest
from factories import FIXTURES, Project, document, rule_set

from subedit.application import Linter, ReportAggregator, RuleEngine
from subedit.domain import (
    Diagnostic,
    Document,
    ExternalLinter,
    Fix,
    FixKind,
    RuleSet,
    RuleSettings,
    Severity,
    SourceRange,
    apply_edits,
)
from subedit.infrastructure import ALL_RULES, DEFAULT_PARSER, SUFFIX_ALIASES, AutoCorrectLinter, ValeLinter


MIS_WRAPPED = (
    'def f():\n    # cap the size so the mmap does not\n    # blow past it, an unbounded value faults.\n    pass\n'
)


class StubLinter(ExternalLinter):
    def __init__(self, name: str, available: bool = True, diagnostics: tuple[Diagnostic, ...] = ()) -> None:
        self.name = name
        self._available = available
        self._diagnostics = diagnostics
        self.calls = 0

    def is_available(self) -> bool:
        return self._available

    def run(self, document: Document) -> tuple[Diagnostic, ...]:
        self.calls += 1
        return self._diagnostics


def finding(rule_id: str, start: int = 0, source: str = 'stub') -> Diagnostic:
    return Diagnostic(
        rule_id=rule_id,
        range=SourceRange(start, start + 1),
        message='from an external tool',
        fix=Fix.rewrite(),
        source=source,
    )


def aggregate(linters, text: str = MIS_WRAPPED, width: int = 60):
    core = Linter(DEFAULT_PARSER, RuleEngine(ALL_RULES))
    return ReportAggregator(core, linters).run(document(text), rule_set(width=width))


def test_native_findings_survive_with_no_linters() -> None:
    report = aggregate(())
    assert report.diagnostics
    assert all(item.source == 'subedit' for item in report.diagnostics)


def test_external_findings_are_merged_in() -> None:
    report = aggregate((StubLinter('stub', diagnostics=(finding('stub.Rule'),)),))
    assert 'stub.Rule' in [item.rule_id for item in report.diagnostics]


def test_an_unavailable_linter_is_recorded_rather_than_fatal() -> None:
    linter = StubLinter('absent', available=False, diagnostics=(finding('never'),))
    report = aggregate((linter,))
    assert report.unavailable_sources == ('absent',)
    assert linter.calls == 0
    assert report.diagnostics


def test_identical_findings_from_two_sources_are_deduplicated() -> None:
    shared = finding('same.Rule', start=0)
    report = aggregate((StubLinter('a', diagnostics=(shared,)), StubLinter('b', diagnostics=(shared,))))
    assert [item.rule_id for item in report.diagnostics].count('same.Rule') == 1


def test_findings_differing_by_position_are_both_kept() -> None:
    linter = StubLinter('a', diagnostics=(finding('same.Rule', 0), finding('same.Rule', 40)))
    report = aggregate((linter,))
    assert [item.rule_id for item in report.diagnostics].count('same.Rule') == 2


def test_external_rewrite_findings_reach_the_author_partition() -> None:
    report = aggregate((StubLinter('a', diagnostics=(finding('stub.Rule'),)),))
    assert 'stub.Rule' in [item.rule_id for item in report.needing_author]


def test_mechanical_and_authored_findings_stay_separated() -> None:
    report = aggregate((StubLinter('a', diagnostics=(finding('stub.Rule'),)),))
    assert all(item.fix and item.fix.kind is FixKind.REFLOW for item in report.mechanical)
    assert all(item.needs_author for item in report.needing_author)


def test_a_clean_document_with_a_silent_linter_is_clean() -> None:
    report = aggregate((StubLinter('a'),), text='def f():\n    # short and fine.\n    pass\n')
    assert report.is_clean


def test_the_project_config_tunes_a_delegated_rule() -> None:
    linter = StubLinter('stub', diagnostics=(finding('stub.Loud', 0), finding('stub.Quiet', 2)))
    core = Linter(DEFAULT_PARSER, RuleEngine(ALL_RULES))
    rules = dataclasses.replace(
        rule_set(settings={'stub.Loud': RuleSettings(severity=Severity.WARNING)}),
        disabled_external_ids=frozenset({'stub.Quiet'}),
    )
    report = ReportAggregator(core, (linter,)).run(document('x = 1\n'), rules)

    assert [(item.rule_id, item.severity) for item in report.diagnostics] == [('stub.Loud', Severity.WARNING)]
    assert not report.blocking, 'a warning reaches the author as advice, not as a block'


@pytest.mark.skipif(shutil.which('vale') is None, reason='vale is not installed')
def test_the_vale_adapter_normalises_real_output(project: Project) -> None:
    target = project.write('probe.py', 'def f():\n    # a semicolon; which is forbidden here.\n    pass\n')

    found = ValeLinter().run(
        Document(uri=target.resolve().as_uri(), text=target.read_text(encoding='utf-8'), language_id='python')
    )
    assert any('Semicolon' in item.rule_id for item in found)
    assert all(item.source == 'vale' for item in found)
    assert all(item.fix and item.fix.kind is FixKind.REWRITE for item in found)


def test_adapters_report_absence_without_raising() -> None:
    assert ValeLinter(executable='definitely-not-installed').is_available() is False
    missing = Document(uri='file:///nowhere/gone.py', text='# note\n', language_id='python')
    assert ValeLinter(executable='definitely-not-installed').run(missing) == ()


@pytest.mark.skipif(shutil.which('vale') is None, reason='vale is not installed')
def test_a_repo_without_a_vale_config_gets_the_bundled_one(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.delenv('VALE_CONFIG_PATH', raising=False)
    linter = ValeLinter()
    text = 'def f():\n    # a semicolon; which is forbidden here.\n    pass\n'
    for name in ('first.py', 'second.py'):
        found = linter.run(Document(uri=(tmp_path / name).as_uri(), text=text, language_id='python'))
        assert any('Semicolon' in item.rule_id for item in found)


def test_vale_counts_as_missing_until_the_extra_has_downloaded_it(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    project.write('__init__.py', '')
    placeholder = project.write('vale_bin', '#!/bin/sh\n')
    found_spec = importlib.machinery.ModuleSpec('vale', None, origin=str(project.root / '__init__.py'))
    monkeypatch.setattr(importlib.util, 'find_spec', lambda name: found_spec if name == 'vale' else None)
    linter = ValeLinter(executable='sh')

    assert linter.is_available() is False, 'a first edit must not wait while the extra downloads Vale'
    placeholder.write_bytes(b'\0' * 4096)
    assert linter.is_available() is True


@pytest.mark.skipif(shutil.which('vale') is None, reason='vale is not installed')
def test_vale_findings_inside_a_code_span_are_dropped(tmp_path: pathlib.Path) -> None:
    text = 'def f():\n    """Parse it.\n\n    For example ``zh-TW,zh;q=0.9`` and `a;b` are headers; this is prose.\n    """\n'
    found = ValeLinter().run(Document(uri=(tmp_path / 'probe.py').as_uri(), text=text, language_id='python'))
    semicolons = [item for item in found if 'Semicolon' in item.rule_id]
    assert [text[item.range.start] for item in semicolons] == [';'], 'code is not prose, so only the last one counts'
    assert text.index('headers;') + len('headers') == semicolons[0].range.start


@pytest.mark.skipif(shutil.which('vale') is None, reason='vale is not installed')
def test_vale_findings_inside_an_example_block_are_dropped(tmp_path: pathlib.Path) -> None:
    text = 'def f():\n    """Parse it.\n\n    Run it like this:\n\n        parse(a); parse(b)\n    """\n'
    linter = ReportAggregator(Linter(DEFAULT_PARSER, RuleEngine(ALL_RULES)), (ValeLinter(),))
    report = linter.run(
        Document(uri=(tmp_path / 'probe.py').as_uri(), text=text, language_id='python'),
        RuleSet(enabled_rule_ids=frozenset()),
    )
    assert not [item for item in report.diagnostics if 'Semicolon' in item.rule_id], 'an example is code, not prose'


@pytest.mark.skipif(shutil.which('vale') is None, reason='vale is not installed')
@pytest.mark.parametrize('suffix', ['.ts', '.mts', '.cts'])
def test_vale_reads_only_the_comments_of_a_typescript_module(tmp_path: pathlib.Path, suffix: str) -> None:
    text = 'const a = "x; y"; // a note; with a semicolon\n'
    linter = ValeLinter(suffix_aliases=SUFFIX_ALIASES)
    found = linter.run(Document(uri=(tmp_path / f'a{suffix}').as_uri(), text=text, language_id='typescript'))
    assert [text[item.range.start] for item in found if 'Semicolon' in item.rule_id] == [';']


def test_autocorrect_never_edits_a_string_in_code() -> None:
    text = 'def f():\n    # 註解English文字\n    return "中文English"  # 尾註English\n'
    linter = ReportAggregator(Linter(DEFAULT_PARSER, RuleEngine(ALL_RULES)), (AutoCorrectLinter(),))
    report = linter.run(
        Document(uri='file:///probe.py', text=text, language_id='python'), RuleSet(enabled_rule_ids=frozenset())
    )
    source = text.encode('utf-8')
    edited = [source[item.range.start : item.range.end].decode('utf-8') for item in report.diagnostics]
    assert edited == ['    # 註解English文字'], 'a string is code, and changing it changes what the program does'


def test_a_file_autocorrect_cannot_parse_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    def give_up(text: str, path: str) -> str:
        raise ValueError('call limit reached')

    monkeypatch.setattr('autocorrect_py.format_for', give_up)
    assert AutoCorrectLinter().run(Document(uri='file:///big.ts', text='// 註解\n', language_id='typescript')) == ()


def test_autocorrect_needs_no_install() -> None:
    assert AutoCorrectLinter().is_available() is True


@pytest.mark.skipif(shutil.which('vale') is None, reason='vale is not installed')
def test_the_vale_adapter_lints_the_text_it_is_given_rather_than_the_disk(project: Project) -> None:
    target = project.write('probe.py', 'def f():\n    pass\n')
    unsaved = 'def f():\n    # a semicolon; which is forbidden here.\n    pass\n'

    found = ValeLinter().run(Document(uri=target.resolve().as_uri(), text=unsaved, language_id='python'))
    assert any('Semicolon' in item.rule_id for item in found)


def test_the_autocorrect_adapter_offers_an_edit_for_text_never_saved() -> None:
    # The unspaced sample lives in an excluded fixture, so checking this repository does not flag it.
    text = (FIXTURES / 'autocorrect' / 'unspaced.py').read_text(encoding='utf-8')
    found = AutoCorrectLinter().run(Document(uri='file:///nowhere/probe.py', text=text, language_id='python'))

    assert len(found) == 1
    assert found[0].fix is not None and found[0].fix.kind is FixKind.TARGETED
    assert found[0].fix.edits[0].new_text == '# 今天下午 3 點開會'


def test_autocorrect_edits_the_line_it_corrected_past_a_record_separator() -> None:
    text = "const FORMAT = '%H\x1e%s'\n// 使用sse传输\n"
    found = AutoCorrectLinter().run(Document(uri='file:///probe.ts', text=text, language_id='typescript'))
    assert [apply_edits(text, item.fix.edits) for item in found if item.fix] == [
        "const FORMAT = '%H\x1e%s'\n// 使用 sse 传输\n"
    ]


@pytest.mark.skipif(shutil.which('vale') is None, reason='vale is not installed')
@pytest.mark.parametrize(
    ('text', 'language_id', 'suffix'),
    [
        (
            '// @ts-expect-error the source has no types; callers exercise it.\nimport { a } from "./a.mjs";\n',
            'typescript',
            '.ts',
        ),
        ('import os  # noqa: F401 kept for its side effect; nothing calls it\n', 'python', '.py'),
    ],
)
def test_vale_leaves_a_directive_alone_as_the_native_rules_do(
    tmp_path: pathlib.Path, text: str, language_id: str, suffix: str
) -> None:
    linter = ReportAggregator(
        Linter(DEFAULT_PARSER, RuleEngine(ALL_RULES)), (ValeLinter(suffix_aliases=SUFFIX_ALIASES),)
    )
    report = linter.run(
        Document(uri=(tmp_path / f'a{suffix}').as_uri(), text=text, language_id=language_id),
        rule_set(),
    )
    assert report.diagnostics == (), 'a tool reads the directive, so no rule reads its reason as prose'
