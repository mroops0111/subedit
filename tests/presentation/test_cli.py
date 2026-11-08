import pathlib

import pytest
from factories import Project

from subedit.domain import Diagnostic, Document, ExternalLinter
from subedit.presentation import cli
from subedit.presentation.cli import app


def test_version_prints_the_package_version(capsys: pytest.CaptureFixture[str]) -> None:
    from subedit import __version__

    with pytest.raises(SystemExit) as exit_info:
        app(['version'])
    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_stats_reports_a_measured_corpus(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    source = project.write('sample.py', 'def build():\n    """Public doc."""\n    # inline note\n')

    with pytest.raises(SystemExit) as exit_info:
        app(['stats', str(source)])
    assert exit_info.value.code == 0

    output = capsys.readouterr().out
    assert '1 documents, 2 comment blocks' in output
    assert 'doc/public' in output
    assert 'plain/inline-body' in output


def test_stats_exits_non_zero_when_nothing_is_readable(tmp_path: pathlib.Path) -> None:
    with pytest.raises(SystemExit) as exit_info:
        app(['stats', str(tmp_path)])
    assert exit_info.value.code == 1


def test_check_reports_findings_and_exits_non_zero(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    target = project.write(
        'bad.py',
        'def f():\n    # cap the size so the mmap does not\n    # blow past it, an unbounded value faults.\n    pass\n',
    )
    project.write('subedit.toml', '[subedit]\nline-width = 60\n')

    with pytest.raises(SystemExit) as exit_info:
        app(['check', str(target)])
    assert exit_info.value.code == 1
    assert 'mid-clause-break' in capsys.readouterr().out


def test_check_on_clean_input_exits_zero(project: Project) -> None:
    target = project.write('good.py', 'def f():\n    # short and fine.\n    pass\n')
    with pytest.raises(SystemExit) as exit_info:
        app(['check', str(target)])
    assert exit_info.value.code == 0


def test_check_rejects_an_unknown_output_format(project: Project) -> None:
    target = project.write('a.py', '# note\n')
    with pytest.raises(SystemExit) as exit_info:
        app(['check', str(target), '--output', 'nonsense'])
    assert exit_info.value.code == 2


@pytest.mark.parametrize('command', ['check', 'fix', 'stats'])
def test_a_config_written_wrong_stops_every_command(
    project: Project, capsys: pytest.CaptureFixture[str], command: str
) -> None:
    project.write('subedit.toml', '[rules]\nline-too-short = { minimum_characters = 30 }\n')
    target = project.write('a.py', '# note\n')
    with pytest.raises(SystemExit) as exit_info:
        app([command, str(target)])
    assert exit_info.value.code == 2
    assert 'minimum_characters: is not an option of line-too-short' in capsys.readouterr().err


def test_fix_prints_a_diff_without_write(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    original = (
        'def f():\n    # cap the size so the mmap does not\n    # blow past it, an unbounded value faults.\n    pass\n'
    )
    target = project.write('bad.py', original)
    project.write('subedit.toml', '[subedit]\nline-width = 60\n')

    with pytest.raises(SystemExit):
        app(['fix', str(target)])
    assert '---' in capsys.readouterr().out
    assert target.read_text(encoding='utf-8') == original


def test_fix_write_applies_the_change(project: Project) -> None:
    original = (
        'def f():\n    # cap the size so the mmap does not\n    # blow past it, an unbounded value faults.\n    pass\n'
    )
    target = project.write('bad.py', original)
    project.write('subedit.toml', '[subedit]\nline-width = 60\n')

    with pytest.raises(SystemExit):
        app(['fix', str(target), '--write'])
    assert target.read_text(encoding='utf-8') != original
    assert 'does not blow past it,' in target.read_text(encoding='utf-8')


def test_the_actionable_format_shows_only_findings_needing_an_author(
    project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    target = project.write(
        'a.py',
        'def f():\n    # this single sentence has no comma anywhere and runs well past the budget here.\n    pass\n',
    )
    project.write('subedit.toml', '[subedit]\nline-width = 50\n')

    with pytest.raises(SystemExit):
        app(['check', str(target), '--output', 'actionable'])
    output = capsys.readouterr().out
    assert 'unbreakable-sentence' in output
    assert 'do not add a suppression comment' in output


def test_the_json_format_encodes_ranges_and_fix_kind(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    import json

    target = project.write(
        'a.py',
        'def f():\n    # cap the size so the mmap does not\n    # blow past it, an unbounded value faults.\n    pass\n',
    )
    project.write('subedit.toml', '[subedit]\nline-width = 60\n')

    with pytest.raises(SystemExit):
        app(['check', str(target), '--output', 'json'])
    text = json.loads(capsys.readouterr().out)
    assert text['diagnostics'][0]['fixKind'] == 'reflow'
    assert text['diagnostics'][0]['mechanical'] is True


def test_the_actionable_format_says_so_when_only_mechanical_findings_exist(
    project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    target = project.write(
        'a.py',
        'def f():\n    # cap the size so the mmap does not\n    # blow past it, an unbounded value faults.\n    pass\n',
    )
    project.write('subedit.toml', '[subedit]\nline-width = 60\n')

    with pytest.raises(SystemExit):
        app(['check', str(target), '--output', 'actionable'])
    output = capsys.readouterr().out
    assert 'Nothing needs rewriting' in output
    assert 'repaired mechanically' in output


def test_the_actionable_format_says_so_when_nothing_is_wrong(
    project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    target = project.write('a.py', 'def f():\n    # short and fine.\n    pass\n')

    with pytest.raises(SystemExit):
        app(['check', str(target), '--output', 'actionable'])
    assert 'No findings' in capsys.readouterr().out


@pytest.mark.parametrize('ready_after_prepare', [True, False])
def test_check_prepares_delegated_tools_and_says_when_one_is_missing(
    project: Project,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    ready_after_prepare: bool,
) -> None:
    probe = _PreparedLinter(ready_after_prepare)
    monkeypatch.setattr(cli, 'EXTERNAL_LINTERS', (probe,))
    source = project.write('sample.py', 'def build():\n    pass\n')

    with pytest.raises(SystemExit):
        app(['check', str(source)])

    assert probe.prepared, 'a command waits for what a delegated tool needs, unlike the hook'
    warned = 'probe is not installed' in capsys.readouterr().err
    assert warned is not ready_after_prepare, 'a skipped tool must not read as a clean run'


def test_check_passes_when_only_warnings_remain(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    source = project.write('sample.py', '# A banner about the module.\n\nVALUE = 1\n')

    with pytest.raises(SystemExit) as exit_info:
        app(['check', str(source), '--no-delegate'])

    assert 'warning  file-header-comment' in capsys.readouterr().out
    assert exit_info.value.code == 0, 'a warning shows in the output but does not fail the run'


def test_a_diff_keeps_a_blank_last_context_line(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    target = project.write(
        'bad.py',
        'def f():\n    # cap the size so the mmap does not\n    # blow past it, an unbounded value faults.\n    pass\n\n\nx = 1\n',
    )
    project.write('subedit.toml', '[subedit]\nline-width = 60\n')

    with pytest.raises(SystemExit):
        app(['fix', '--no-delegate', str(target)])
    hunk = capsys.readouterr().out.split('@@')[-1]
    assert hunk.endswith('\n \n'), 'patch counts a blank context line, so dropping it makes the hunk short'


def test_fix_write_lays_out_the_message_a_commit_msg_hook_hands_it(project: Project) -> None:
    project.write('subedit.toml', '')
    message = project.write('.git/COMMIT_EDITMSG', 'Fix the parser.\nIt dropped a line.\n')
    with pytest.raises(SystemExit) as exit_info:
        app(['fix', '--write', '--no-delegate', str(message)])
    assert exit_info.value.code == 0
    assert message.read_text(encoding='utf-8') == 'Fix the parser\n\nIt dropped a line.\n'


class _PreparedLinter(ExternalLinter):
    name = 'probe'

    def __init__(self, ready_after_prepare: bool) -> None:
        self._ready_after_prepare = ready_after_prepare
        self.prepared = False

    def prepare(self) -> None:
        self.prepared = True

    def is_available(self) -> bool:
        return self.prepared and self._ready_after_prepare

    def run(self, document: Document) -> tuple[Diagnostic, ...]:
        return ()
