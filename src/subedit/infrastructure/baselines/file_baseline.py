import pathlib

from ...domain.models.baseline import Baseline
from ...domain.ports.baseline_source import BaselineSource


class FileBaseline(BaselineSource):
    """The text of one file, which a single draft or file is compared against, with no git involved."""

    def __init__(self, text: str) -> None:
        self._text = text

    def baseline_for(self, path: pathlib.Path) -> Baseline:
        return Baseline(self._text)
