import dataclasses

from .comment import CommentGroup, CommentPlacement
from .diagnostic import Diagnostic
from .position import SourceRange


@dataclasses.dataclass(frozen=True, slots=True)
class ProseMap:
    """Where a document holds prose an outside checker may read and edit, and where that prose holds code instead.

    A prose checker such as Vale or AutoCorrect reads the whole file,
    so what it finds outside these regions concerns code nobody asked it about.
    """

    editable: tuple[SourceRange, ...] = ()
    code: tuple[SourceRange, ...] = ()

    @classmethod
    def of_comments(cls, groups: tuple[CommentGroup, ...]) -> 'ProseMap':
        """A trailing comment shares its line with code, so only a comment standing on its own lines is editable."""
        return cls(
            editable=tuple(
                line.range
                for group in groups
                if group.placement is not CommentPlacement.TRAILING
                for line in group.lines
            ),
            code=tuple(code_range for group in groups for code_range in group.code_ranges()),
        )

    def admits(self, diagnostic: Diagnostic) -> bool:
        """Whether a finding reads prose rather than code, and any edit it offers stays on lines of prose."""
        if any(code_range.start <= diagnostic.range.start < code_range.end for code_range in self.code):
            return False
        if diagnostic.fix is None:
            return True
        return all(
            any(line.start <= edit.range.start and edit.range.end <= line.end for line in self.editable)
            for edit in diagnostic.fix.edits
        )
