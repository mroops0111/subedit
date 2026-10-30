import json
import pathlib
import subprocess
import typing

import pytest
from factories import REPOSITORY_ROOT, Project

from subedit.presentation.harnesses.claude_code_harness import EDIT_TOOLS


PLUGIN = REPOSITORY_ROOT / 'plugins' / 'subedit'
MANIFEST = PLUGIN / '.claude-plugin' / 'plugin.json'
MARKETPLACE = REPOSITORY_ROOT / '.claude-plugin' / 'marketplace.json'
HOOKS = PLUGIN / 'hooks' / 'hooks.json'
WRAPPER = PLUGIN / 'scripts' / 'run-subedit-hook.sh'
WRAPPER_COMMAND = f'"${{CLAUDE_PLUGIN_ROOT}}"/scripts/{WRAPPER.name}'


def load(path: pathlib.Path) -> typing.Any:
    return json.loads(path.read_text(encoding='utf-8'))


@pytest.mark.parametrize('path', [MANIFEST, MARKETPLACE, HOOKS])
def test_every_plugin_file_is_valid_json(path: pathlib.Path) -> None:
    assert isinstance(load(path), dict)


def test_the_manifest_names_the_plugin() -> None:
    assert load(MANIFEST)['name'] == 'subedit'


def test_the_manifest_version_matches_the_package() -> None:
    pyproject = (REPOSITORY_ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    declared = next(line for line in pyproject.splitlines() if line.startswith('version'))

    assert load(MANIFEST)['version'] in declared, 'a plugin claiming a different version misleads whoever installs it'


def test_the_hook_matcher_covers_every_tool_the_harness_recognises() -> None:
    entries = load(HOOKS)['hooks']['PostToolUse']
    matched = set(entries[0]['matcher'].split('|'))

    assert matched == EDIT_TOOLS, 'a tool the harness reads but the matcher omits never reaches the hook'


def test_the_hook_runs_the_wrapper_from_the_plugin_directory() -> None:
    command = load(HOOKS)['hooks']['PostToolUse'][0]['hooks'][0]['command']

    assert command == WRAPPER_COMMAND, 'a bare or unquoted path breaks once the plugin is installed elsewhere'


def test_the_wrapper_is_executable() -> None:
    assert WRAPPER.stat().st_mode & 0o111, 'a wrapper without the execute bit fails only once installed'


def test_the_wrapper_is_valid_shell() -> None:
    subprocess.run(['bash', '-n', str(WRAPPER)], check=True, capture_output=True)


def run_wrapper(project: pathlib.Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ['bash', str(WRAPPER), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env={'PATH': '/usr/bin:/bin', 'CLAUDE_PROJECT_DIR': str(project)},
        input='',
    )


def test_the_wrapper_says_what_to_install_when_nothing_is_found(project: Project) -> None:
    project.write('subedit.toml', '[subedit]\n')

    completed = run_wrapper(project.root)

    assert completed.returncode == 1
    assert 'astral.sh/uv' in completed.stderr, 'a missing command must say how to get it'


@pytest.mark.parametrize('arguments', [(), ('prepare',)])
def test_the_wrapper_stays_out_of_a_project_without_subedit_config(
    project: Project, arguments: tuple[str, ...]
) -> None:
    project.write('pyproject.toml', '[tool.ruff]\nline-length = 100\n')

    completed = run_wrapper(project.root, *arguments)

    assert (completed.returncode, completed.stderr) == (0, '')


@pytest.mark.parametrize('config', [('subedit.toml', '[subedit]\n'), ('pyproject.toml', '[tool.subedit.rules]\n')])
def test_the_wrapper_acts_in_a_subdirectory_of_a_configured_project(project: Project, config: tuple[str, str]) -> None:
    name, text = config
    project.write(name, text)
    (project.root / 'packages').mkdir()

    assert 'astral.sh/uv' in run_wrapper(project.root / 'packages').stderr


def test_the_wrapper_runs_the_released_version() -> None:
    pyproject = (REPOSITORY_ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    version = next(line for line in pyproject.splitlines() if line.startswith('version')).split('"')[1]

    assert f"SPEC='subedit[vale]>={version}'" in WRAPPER.read_text(encoding='utf-8'), (
        'a plugin pinned below the package it ships with runs an older release than this one'
    )


def test_a_session_start_warms_the_same_wrapper() -> None:
    command = load(HOOKS)['hooks']['SessionStart'][0]['hooks'][0]['command']

    assert command == f'{WRAPPER_COMMAND} prepare'


def test_the_marketplace_points_at_the_plugin_directory() -> None:
    listed = load(MARKETPLACE)['plugins']

    assert [plugin['name'] for plugin in listed] == ['subedit']
    assert (REPOSITORY_ROOT / listed[0]['source']).resolve() == PLUGIN, (
        'a relative source resolves from the marketplace root'
    )


def test_the_plugin_carries_everything_it_runs() -> None:
    """An install copies only the plugin directory, so nothing it loads may live outside it."""
    assert {path.name for path in PLUGIN.iterdir()} == {'.claude-plugin', 'hooks', 'scripts', 'skills'}
    assert [path.name for path in (PLUGIN / '.claude-plugin').iterdir()] == ['plugin.json']


def test_the_judging_skill_names_itself_as_its_folder_does() -> None:
    skill = PLUGIN / 'skills' / 'judging-findings' / 'SKILL.md'
    front_matter = skill.read_text(encoding='utf-8').split('---')[1]

    assert 'name: judging-findings' in front_matter, 'Claude Code loads a skill by the name in its front matter'
    assert 'description:' in front_matter
