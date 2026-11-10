import pathlib

import pytest
from factories import Project


@pytest.fixture
def project(tmp_path: pathlib.Path) -> Project:
    return Project(tmp_path)


@pytest.fixture
def repository(project: Project, monkeypatch: pytest.MonkeyPatch) -> Project:
    """A project that is also a git working tree with one commit, so HEAD exists.

    git reads no global or system config here, so a hook path set on the machine never receives a test's hook.
    """
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', '/dev/null')
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    project.git('init', '-q')
    project.git('commit', '-q', '--allow-empty', '-m', 'Start the repository')
    return project
