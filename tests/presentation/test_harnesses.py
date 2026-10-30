import pathlib
import typing

import pytest
from factories import Project

from subedit.presentation.harnesses import ALL_HARNESSES, ClaudeCodeHarness, CodexHarness, HarnessMetadata, resolve


@pytest.fixture
def source(project: Project) -> pathlib.Path:
    target = project.write('module.py', '# a note\n')
    return target


def name_of(payload: typing.Mapping[str, object]) -> str:
    resolved = resolve(payload)
    assert resolved is not None, 'no harness recognised the payload'
    return resolved[0].metadata.name


def edited_files_of(payload: typing.Mapping[str, object]) -> tuple[pathlib.Path, ...]:
    resolved = resolve(payload)
    return resolved[1] if resolved else ()


def test_claude_code_reads_the_named_file(source: pathlib.Path) -> None:
    payload = {'tool_name': 'Edit', 'tool_input': {'file_path': str(source)}}

    assert name_of(payload) == 'claude-code'
    assert edited_files_of(payload) == (source,)


@pytest.mark.parametrize(
    'patch',
    [
        '*** Update File: {path}\n@@\n-old\n+new\n',
        '--- a/{path}\n+++ b/{path}\n@@\n',
        '--- {path}\n+++ {path}\n',
    ],
)
def test_codex_recovers_the_path_from_the_patch_body(source: pathlib.Path, patch: str) -> None:
    payload = {'tool_name': 'apply_patch', 'tool_input': {'command': patch.format(path=source)}}

    assert name_of(payload) == 'codex'
    assert edited_files_of(payload) == (source,)


def test_codex_ignores_the_dev_null_side_of_an_addition(source: pathlib.Path) -> None:
    payload = {'tool_name': 'apply_patch', 'tool_input': {'command': f'--- /dev/null\n+++ {source}\n'}}
    assert edited_files_of(payload) == (source,)


def test_declining_differs_from_finding_nothing(project: Project) -> None:
    notebook = project.write('a.ipynb', '{}')
    ours = {'tool_name': 'NotebookEdit', 'tool_input': {'notebook_path': str(notebook)}}
    not_ours = {'tool_name': 'Bash', 'tool_input': {'command': 'ls'}}

    recognised = resolve(ours)
    assert recognised is not None, 'a notebook edit came from Claude Code even when we check nothing in it'
    assert recognised[1] == ()
    assert resolve(not_ours) is None, 'a shell call was never ours to read'


def test_a_payload_no_harness_recognises_resolves_to_nothing() -> None:
    assert resolve({}) is None
    assert resolve({'tool_name': 'Read', 'tool_input': {'file_path': 'a.py'}}) is None


def test_a_missing_file_is_dropped(tmp_path: pathlib.Path) -> None:
    payload = {'tool_name': 'Edit', 'tool_input': {'file_path': str(tmp_path / 'gone.py')}}
    assert edited_files_of(payload) == ()


def test_a_file_of_another_language_is_dropped(project: Project) -> None:
    other = project.write('notes.txt', 'heading\n')
    payload = {'tool_name': 'Edit', 'tool_input': {'file_path': str(other)}}
    assert edited_files_of(payload) == ()


def test_the_same_path_named_twice_is_visited_once(source: pathlib.Path) -> None:
    payload = {'tool_name': 'apply_patch', 'tool_input': {'command': f'--- {source}\n+++ {source}\n'}}
    assert edited_files_of(payload) == (source,)


def test_every_harness_describes_itself() -> None:
    for harness in ALL_HARNESSES:
        assert harness.metadata.summary
        assert harness.metadata.example


def test_each_example_is_recognised_by_the_harness_that_published_it() -> None:
    for harness in ALL_HARNESSES:
        assert name_of(harness.metadata.example) == harness.metadata.name, (
            'a published example nobody feeds back is documentation that can rot'
        )


def test_a_harness_must_name_itself() -> None:
    with pytest.raises(ValueError, match='names itself'):
        HarnessMetadata(name='', summary='something', example={})


def test_the_registry_holds_both_agents() -> None:
    assert [type(harness) for harness in ALL_HARNESSES] == [ClaudeCodeHarness, CodexHarness]
