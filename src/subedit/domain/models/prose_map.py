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
    # Every unit whole, since a checker that reads a file type as plain text also reads its keys and values.
    prose: tuple[SourceRange, ...] = ()

    @classmethod
    def of_units(cls, units: tuple[ProseUnit, ...], skipped: tuple[SourceRange, ...] = ()) -> 'ProseMap':
        """What a document's units hold, with the stretches its parser skipped counted as code.

        A quotation holds someone else's words, so a checker leaves it as written too.
        """
        return cls(
            editable=tuple(region for unit in units if not unit.is_quoted for region in unit.editable_ranges()),
            code=(
                *(region for unit in units for region in unit.code_ranges()),
                *(unit.range for unit in units if unit.is_quoted),
                *skipped,
            ),
            prose=tuple(unit.range for unit in units),
        )

    def admits(self, diagnostic: Diagnostic) -> bool:
        """Whether a finding reads prose rather than code, and any edit it offers stays on lines of prose."""
        start = diagnostic.range.start
        if not any(region.start <= start < region.end for region in self.prose):
            return False
        if any(region.start <= start < region.end for region in self.code):
            return False
        if diagnostic.fix is None:
            return True
        return all(
            any(line.start <= edit.range.start and edit.range.end <= line.end for line in self.editable)
            for edit in diagnostic.fix.edits
        )
