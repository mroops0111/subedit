import dataclasses
import functools

from .position import PositionMap


@dataclasses.dataclass(frozen=True)
class Document:
    """A file in memory, whose version counts the edits applied to it."""

    uri: str
    text: str
    language_id: str
    version: int = 0

    @functools.cached_property
    def positions(self) -> PositionMap:
        return PositionMap(self.text)

    def with_text(self, text: str, version: int | None = None) -> 'Document':
        return dataclasses.replace(
            self,
            text=text,
            version=self.version + 1 if version is None else version,
        )
