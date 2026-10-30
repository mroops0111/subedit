import json
import pathlib
import subprocess
import sys

import pytest
from factories import Project

from subedit.presentation import hook


CONFIG = '[subedit]\nline-width = 74\n'
MIS_WRAPPED = (
    'def f():\n'
    '    # cap the size to the shared limit so the mmap does not\n'
    '    # blow past it, an unbounded value faults the runner.\n'
    '    pass\n'
)
UNBREAKABLE = (
    'def f():\n    # this one carries no comma at all and runs a very long way past the budget here.\n    pass\n'
)


def payload(path: pathlib.Path, tool: str = 'Edit') -> dict[str, object]:
    return {'tool_name': tool, 'tool_input': {'file_path': str(path)}}


def seed(project: Project, body: str, name: str = 'probe.py') -> pathlib.Path:
    project.write('subedit.toml', CONFIG)
    return project.write(name, body)


def test_a_project_without_subedit_config_is_left_alone(project: Project) -> None:
    body = MIS_WRAPPED + 'def g():\n    # this one carries no comma and runs on' + ' and on' * 16 + '.\n    pass\n'
    target = project.write('probe.py', body)

    hook_result = hook.run(payload(target))

    assert hook_result.exit_code == 0
    assert target.read_text(encoding='utf-8') == body


def test_a_tool_subedit_table_in_pyproject_opts_in(project: Project) -> None:
    project.write('pyproject.toml', '[tool.subedit]\nline-width = 74\n')
    target = project.write('probe.py', UNBREAKABLE)

    assert hook.run(payload(target), write=False).is_blocking


def test_a_non_edit_tool_is_ignored(project: Project) -> None:
    target = seed(project, MIS_WRAPPED)
    assert hook.run(payload(target, tool='Read')).exit_code == 0


def test_a_file_in_no_known_language_is_ignored(project: Project) -> None:
    target = project.write('notes.txt', 'heading\n')
    assert hook.edited_files(payload(target)) == ()


def test_a_missing_file_is_ignored(tmp_path: pathlib.Path) -> None:
    assert hook.edited_files(payload(tmp_path / 'gone.py')) == ()


def test_a_payload_without_a_path_is_ignored() -> None:
    assert hook.run({'tool_name': 'Edit', 'tool_input': {}}).exit_code == 0


def test_mechanical_findings_are_repaired_silently(project: Project) -> None:
    target = seed(project, MIS_WRAPPED)
    outcome = hook.run(payload(target))

    assert outcome.exit_code == 0
    assert not outcome.is_blocking
    assert outcome.stderr == ''
    assert str(target) in outcome.repaired_paths
    assert 'does not blow past it,\n' in target.read_text(encoding='utf-8')


def test_a_rewrite_finding_blocks_with_exit_two(project: Project) -> None:
    target = seed(project, UNBREAKABLE)
    outcome = hook.run(payload(target))

    assert outcome.exit_code == 2
    assert outcome.is_blocking
    assert 'unbreakable-sentence' in outcome.stderr
    assert 'Add a comma' in outcome.stderr


def test_a_clean_file_neither_writes_nor_blocks(project: Project) -> None:
    target = seed(project, 'def f():\n    # short and fine.\n    pass\n')
    original = target.read_text(encoding='utf-8')
    outcome = hook.run(payload(target))

    assert outcome.exit_code == 0
    assert outcome.repaired_paths == ()
    assert target.read_text(encoding='utf-8') == original


def test_a_fixable_neighbour_is_repaired_even_when_the_run_blocks(project: Project) -> None:
    extra = '    # this trailing one carries no comma at all and runs a very long way past the budget here.\n'
    body = MIS_WRAPPED.replace('    pass\n', extra + '    pass\n')
    target = seed(project, body)
    outcome = hook.run(payload(target))

    assert outcome.is_blocking
    assert 'does not blow past it,\n' in target.read_text(encoding='utf-8')


def test_write_can_be_suppressed(project: Project) -> None:
    target = seed(project, MIS_WRAPPED)
    original = target.read_text(encoding='utf-8')
    hook.run(payload(target), write=False)
    assert target.read_text(encoding='utf-8') == original


@pytest.mark.parametrize('body', ['not json at all', '[]', '"a string"'])
def test_malformed_input_never_blocks(body: str) -> None:
    result = subprocess.run(
        [sys.executable, '-m', 'subedit.presentation.hook'],
        input=body,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


def test_the_entry_point_blocks_on_a_rewrite_finding(project: Project) -> None:
    target = seed(project, UNBREAKABLE)
    result = subprocess.run(
        [sys.executable, '-m', 'subedit.presentation.hook'],
        input=json.dumps(payload(target)),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert 'unbreakable-sentence' in result.stderr


def test_the_hook_stays_silent_on_mechanical_findings_even_now(project: Project) -> None:
    target = seed(project, MIS_WRAPPED)
    outcome = hook.run(payload(target))
    assert outcome.stderr == '', 'the hook must never narrate a repair it made silently'
    assert outcome.exit_code == 0


def test_a_codex_patch_reaches_the_same_loop(project: Project) -> None:
    target = seed(project, UNBREAKABLE)
    patch = f'*** Update File: {target}\n@@\n-old\n+new\n'
    outcome = hook.run({'tool_name': 'apply_patch', 'tool_input': {'command': patch}})

    assert outcome.harness_name == 'codex'
    assert outcome.exit_code == 2
    assert 'unbreakable-sentence' in outcome.stderr


def test_an_unclaimed_payload_does_nothing(project: Project) -> None:
    seed(project, UNBREAKABLE)
    outcome = hook.run({'tool_name': 'Bash', 'tool_input': {'command': 'ls'}})

    assert outcome.exit_code == 0
    assert outcome.harness_name == ''


def test_the_hook_can_list_the_shapes_it_accepts() -> None:
    described = hook.describe_harnesses()

    assert 'claude-code' in described
    assert 'codex' in described
    assert 'exits 0' in described
    assert 'subedit fix' in described, 'a non agent caller needs pointing at the CLI'


def test_a_warning_alone_never_blocks_the_agent(project: Project) -> None:
    target = seed(project, '# A banner about the module.\n\nVALUE = 1\n')
    assert not hook.run(payload(target)).is_blocking


def test_a_warning_reaches_claude_code_without_blocking(project: Project) -> None:
    target = seed(project, '# A banner about the module.\n\nVALUE = 1\n')
    outcome = hook.run(payload(target))

    assert outcome.exit_code == 0
    context = json.loads(outcome.stdout)['hookSpecificOutput']
    assert context['hookEventName'] == 'PostToolUse'
    assert 'file-header-comment' in context['additionalContext']


def test_a_warning_rides_along_when_the_edit_blocks(project: Project) -> None:
    target = seed(project, '# A banner about the module.\n\n' + UNBREAKABLE)
    outcome = hook.run(payload(target))

    assert outcome.is_blocking
    assert 'unbreakable-sentence' in outcome.stderr
    assert 'file-header-comment' in outcome.stderr


def test_codex_has_no_channel_for_a_warning(project: Project) -> None:
    target = seed(project, '# A banner about the module.\n\nVALUE = 1\n')
    patch = f'*** Update File: {target}\n@@\n-old\n+new\n'
    outcome = hook.run({'tool_name': 'apply_patch', 'tool_input': {'command': patch}})

    assert outcome.exit_code == 0
    assert outcome.stdout == ''
