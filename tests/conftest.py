import pathlib

import pytest
from factories import Project


@pytest.fixture
def project(tmp_path: pathlib.Path) -> Project:
    return Project(tmp_path)
