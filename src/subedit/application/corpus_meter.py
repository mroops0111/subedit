import dataclasses
import statistics

from ..domain.models.comment import CommentForm, CommentGroup, CommentPlacement, Visibility
from ..domain.models.document import Document
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
class CorpusStatistics:
    document_count: int
    group_count: int
    line_counts: tuple[Distribution, ...]
    physical_widths: Distribution
    sentence_lengths: Distribution
    unbreakable_counts_by_width: tuple[tuple[int, int], ...]


class CorpusMeter:
    def __init__(
        self, parser: SourceParser[CommentGroup], candidate_widths: tuple[int, ...] = (72, 80, 88, 100, 120)
    ) -> None:
        self._parser = parser
        self._candidate_widths = candidate_widths

    def run(self, documents: tuple[Document, ...]) -> CorpusStatistics:
        grouped_line_counts: dict[str, list[int]] = {}
        physical_widths: list[int] = []
        sentence_lengths: list[int] = []
        unbreakable_counts = dict.fromkeys(self._candidate_widths, 0)
        group_count = 0

        # The measures read a comment's lines against a width, so only files the comment parser reads count.
        documents = tuple(document for document in documents if self._parser.supports(document.language_id))
        for document in documents:
            for group in self._parser.parse(document):
                group_count += 1
                grouped_line_counts.setdefault(self._label_for(group), []).append(group.line_count)
                physical_widths.extend(line.physical_width for line in group.lines)
                for sentence in group.prose().sentences():
                    sentence_lengths.append(len(sentence.text))
                    for width in self._candidate_widths:
                        if self._is_unbreakable(sentence.text, width):
                            unbreakable_counts[width] += 1

        return CorpusStatistics(
            document_count=len(documents),
            group_count=group_count,
            line_counts=tuple(
                Distribution(label, tuple(measurements)) for label, measurements in sorted(grouped_line_counts.items())
            ),
            physical_widths=Distribution('physical-width', tuple(physical_widths)),
            sentence_lengths=Distribution('sentence-length', tuple(sentence_lengths)),
            unbreakable_counts_by_width=tuple(sorted(unbreakable_counts.items())),
        )

    def _label_for(self, group: CommentGroup) -> str:
        if group.form is CommentForm.DOC:
            visibility = Visibility.PUBLIC if group.attaches_to_public_symbol else Visibility.INTERNAL
            return f'doc/{visibility.value}'
        if group.placement is CommentPlacement.FILE_HEADER:
            return 'line/file-header'
        return f'line/{group.placement.value}'

    def _is_unbreakable(self, sentence: str, width: int) -> bool:
        return len(sentence) > width and ',' not in sentence
