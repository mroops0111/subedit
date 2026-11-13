import json

from ..application.corpus_meter import CorpusStatistics, Distribution, OptionStatistics, SurfaceStatistics


# The low end reads against a minimum, such as the shortest line, and the high end against a maximum.
_PERCENTILES = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99)
_LABEL_WIDTH = 24
_OPTION_LABEL_WIDTH = 58


def text(statistics: CorpusStatistics) -> str:
    """Each surface's measurements as tables, for a person to read."""
    return '\n\n'.join(_surface_text(measured) for measured in statistics.surfaces)


def as_json(statistics: CorpusStatistics) -> str:
    """Each surface's measurements as JSON, for a tool such as an agent setting up a project to read."""
    return json.dumps({'surfaces': [_encode_surface(measured) for measured in statistics.surfaces]}, indent=2)


def _surface_text(measured: SurfaceStatistics) -> str:
    lines = [f'{measured.surface}: {measured.document_count} documents, {measured.unit_count} units']
    if measured.line_counts:
        lines.extend(['', 'unit line counts', _heading('group', _LABEL_WIDTH)])
        lines.extend(_row(distribution.label, distribution, _LABEL_WIDTH) for distribution in measured.line_counts)
    distributions = (measured.physical_widths, measured.sentence_lengths)
    for distribution in (distribution for distribution in distributions if distribution.count):
        lines.extend(['', distribution.label, _row('', distribution, _LABEL_WIDTH)])
    lines.extend(['', 'sentences over width with no comma to break at'])
    for width, sentence_count in measured.unbreakable_counts_by_width:
        sentence_total = measured.sentence_lengths.count
        percentage = sentence_count / sentence_total * 100 if sentence_total else 0.0
        lines.append(f'  width {width:3d}  {sentence_count:5d} sentences  {percentage:5.2f}%')
    if measured.options:
        lines.extend(['', 'rule options, with the value the project sets', _heading('option', _OPTION_LABEL_WIDTH)])
        lines.extend(_option_row(option) for option in measured.options)
    return '\n'.join(lines)


def _heading(label: str, label_width: int) -> str:
    return (
        f'{label:{label_width}s} {"n":>6s} {"min":>5s} '
        + ' '.join(f'p{int(fraction * 100):<3d}' for fraction in _PERCENTILES)
        + '  max'
    )


def _row(label: str, distribution: Distribution, label_width: int) -> str:
    cells = ' '.join(f'{distribution.percentile(fraction):<4d}' for fraction in _PERCENTILES)
    return f'{label:{label_width}s} {distribution.count:6d} {distribution.minimum:5d} {cells} {distribution.maximum:4d}'


def _option_row(measured: OptionStatistics) -> str:
    label = f'{measured.rule_id} {measured.option.name} = {measured.setting}'
    return _row(label, measured.distribution, _OPTION_LABEL_WIDTH)


def _encode_surface(measured: SurfaceStatistics) -> dict[str, object]:
    return {
        'surface': measured.surface,
        'documents': measured.document_count,
        'units': measured.unit_count,
        'line_counts': {
            distribution.label: _encode_distribution(distribution) for distribution in measured.line_counts
        },
        'physical_widths': _encode_distribution(measured.physical_widths),
        'sentence_lengths': _encode_distribution(measured.sentence_lengths),
        'unbreakable_sentences_by_width': {str(width): count for width, count in measured.unbreakable_counts_by_width},
        'options': [_encode_option(option) for option in measured.options],
    }


def _encode_option(measured: OptionStatistics) -> dict[str, object]:
    return {
        'rule': measured.rule_id,
        'option': measured.option.name,
        'default': measured.option.default,
        'setting': measured.setting,
        'distribution': _encode_distribution(measured.distribution),
    }


def _encode_distribution(distribution: Distribution) -> dict[str, int]:
    return {
        'count': distribution.count,
        'min': distribution.minimum,
        **{f'p{int(fraction * 100)}': distribution.percentile(fraction) for fraction in _PERCENTILES},
        'max': distribution.maximum,
    }
