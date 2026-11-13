import pathlib

from ...domain.models.baseline import Baseline
from ...domain.ports.baseline_source import BaselineSource
from ..git import GitRepository


class GitRevisionBaselineSource(BaselineSource):
    """The text each file had at one commit, so a check reads the prose changed since then.

    With no commit, as in a repository that has none yet, every file is new.
    """

    def __init__(self, repository: GitRepository, commit: str | None) -> None:
        self._repository = repository
        self._commit = commit

    @classmethod
    def at_head(cls, repository: GitRepository) -> 'GitRevisionBaselineSource':
        """The text as last committed, which a first commit has nothing of."""
        return cls(repository, repository.commit_named('HEAD'))

    def baseline_for(self, path: pathlib.Path) -> Baseline:
        if self._commit is None:
            return Baseline('')
        # A file the commit did not hold is new, so all of it counts as changed.
        return Baseline(self._repository.text_at(self._commit, path) or '')
