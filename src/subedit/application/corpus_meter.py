import dataclasses
import statistics

from ..domain.models.document import Document
from ..domain.models.laid_out_prose import LaidOutProse
from ..domain.models.prose_unit import ProseUnit
from ..domain.ports import SourceParser


@dataclasses.dataclass(frozen=True, slots=True)
class Distribution:
    label: str
    measurements: tuple[int, ...]

    @property
    def count(self) -> int:
        return len(self.measurements)

    def percentile(self, fraction: float) -> int:
        if not self.measurements:
            return 0
        sorted_values = sorted(self.measurements)
        position = min(len(sorted_values) - 1, max(0, round(fraction * (len(sorted_values) - 1))))
        return sorted_values[position]

    @property
    def maximum(self) -> int:
        return max(self.measurements, default=0)

    @property
    def median(self) -> int:
        return round(statistics.median(self.measurements)) if self.measurements else 0


@dataclasses.dataclass(frozen=True, slots=True)
class SurfaceStatistics:
    """What one surface's prose measures, where line counts and widths come only from units laid out in lines."""

    surface: str
    document_count: int
    unit_count: int
    line_counts: tuple[Distribution, ...]
    physical_widths: Distribution
    sentence_lengths: Distribution
    unbreakable_counts_by_width: tuple[tuple[int, int], ...]


@dataclasses.dataclass(frozen=True, slots=True)
class CorpusStatistics:
    surfaces: tuple[SurfaceStatistics, ...]

    def for_surface(self, surface: str) -> SurfaceStatistics | None:
        return next((measured for measured in self.surfaces if measured.surface == surface), None)


class CorpusMeter:
    """Measures how long the prose of each surface runs across a corpus, which is where the default limits come from."""

    def __init__(
        self, parser: SourceParser[ProseUnit], candidate_widths: tuple[int, ...] = (72, 80, 88, 100, 120)
    ) -> None:
        self._parser = parser
        self._candidate_widths = candidate_widths

    def run(self, documents: tuple[Document, ...]) -> CorpusStatistics:
        by_surface: dict[str, list[Document]] = {}
        for document in documents:
            file_type = next(
                (file_type for file_type in self._parser.file_types if file_type.language_id == document.language_id),
                None,
            )
            if file_type is not None:
                by_surface.setdefault(file_type.surface, []).append(document)
        return CorpusStatistics(
            tuple(self._measure(surface, tuple(surface_documents)) for surface, surface_documents in by_surface.items())
        )

    def _measure(self, surface: str, documents: tuple[Document, ...]) -> SurfaceStatistics:
        grouped_line_counts: dict[str, list[int]] = {}
        physical_widths: list[int] = []
        sentence_lengths: list[int] = []
        unbreakable_counts = dict.fromkeys(self._candidate_widths, 0)
        unit_count = 0

        for document in documents:
            for unit in self._parser.parse(document):
                unit_count += 1
                for sentence in unit.prose().sentences():
                    sentence_lengths.append(len(sentence.text))
                    for width in self._candidate_widths:
                        if self._is_unbreakable(sentence.text, width):
                            unbreakable_counts[width] += 1
                # Only text laid out in lines against a width has line counts and widths to measure.
                if isinstance(unit, LaidOutProse):
                    grouped_line_counts.setdefault(unit.statistics_category, []).append(unit.line_count)
                    physical_widths.extend(line.physical_width for line in unit.lines)

        return SurfaceStatistics(
            surface=surface,
            document_count=len(documents),
            unit_count=unit_count,
            line_counts=tuple(
                Distribution(label, tuple(measurements)) for label, measurements in sorted(grouped_line_counts.items())
            ),
            physical_widths=Distribution('physical-width', tuple(physical_widths)),
            sentence_lengths=Distribution('sentence-length', tuple(sentence_lengths)),
            unbreakable_counts_by_width=tuple(sorted(unbreakable_counts.items())),
        )

    def _is_unbreakable(self, sentence: str, width: int) -> bool:
        return len(sentence) > width and ',' not in sentence
