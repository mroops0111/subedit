import dataclasses

from .diagnostic import Diagnostic
from .position import SourceRange
from .prose_unit import ProseUnit


@dataclasses.dataclass(frozen=True, slots=True)
class ProseMap:
    """Where a document holds prose an outside checker may read and edit, and where that prose holds code instead.

    A prose checker such as Vale or AutoCorrect reads the whole file,
    so what it finds outside these regions concerns code nobody asked it about.
    """

    editable: tuple[SourceRange, ...] = ()
    code: tuple[SourceRange, ...] = ()
    # A directive's text, such as the reason after @ts-expect-error, is read by a tool, so nothing reads it as prose.
    directives: tuple[SourceRange, ...] = ()

    @classmethod
    def of_units(
        cls,
        units: tuple[ProseUnit, ...],
        directives: tuple[SourceRange, ...] = (),
        literals: tuple[SourceRange, ...] = (),
    ) -> 'ProseMap':
        """What a document's units hold, with any text the document holds outside prose counted as code."""
        return cls(
            directives=directives,
            editable=tuple(region for unit in units for region in unit.editable_ranges()),
            code=(*(region for unit in units for region in unit.code_ranges()), *literals),
        )

    def admits(self, diagnostic: Diagnostic) -> bool:
        """Whether a finding reads prose rather than code, and any edit it offers stays on lines of prose."""
        if any(region.start <= diagnostic.range.start < region.end for region in (*self.code, *self.directives)):
            return False
        if diagnostic.fix is None:
            return True
        return all(
            any(line.start <= edit.range.start and edit.range.end <= line.end for line in self.editable)
            for edit in diagnostic.fix.edits
        )
