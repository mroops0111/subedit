import abc
import pathlib

from ..models.baseline import Baseline


class BaselineSource(abc.ABC):
    """Where the text a file is compared with comes from, such as a git revision or another file."""

    @abc.abstractmethod
    def baseline_for(self, path: pathlib.Path) -> Baseline:
        """The text the file at path is compared with, empty where the file has nothing to compare with."""
        ...
