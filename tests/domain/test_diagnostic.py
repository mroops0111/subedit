import pytest
from factories import edit

from subedit.domain import Diagnostic, Fix, FixKind, Report, RuleMetadata, Severity, SourceRange


def diagnostic(rule_id: str = 'mid-clause-break', start: int = 0, fix: Fix | None = None) -> Diagnostic:
    return Diagnostic(rule_id=rule_id, range=SourceRange(start, start + 1), message='something', fix=fix)


def test_rewrite_carries_no_edits() -> None:
    assert Fix.rewrite().edits == ()
    with pytest.raises(ValueError, match='no edits'):
        Fix(FixKind.REWRITE, (edit(),))


@pytest.mark.parametrize('kind', [FixKind.TARGETED, FixKind.REFLOW])
def test_mechanical_fixes_must_carry_edits(kind: FixKind) -> None:
    with pytest.raises(ValueError, match='at least one edit'):
        Fix(kind, ())


def test_only_rewrite_is_not_mechanical() -> None:
    assert FixKind.TARGETED.is_mechanical
    assert FixKind.REFLOW.is_mechanical
    assert not FixKind.REWRITE.is_mechanical


def test_a_diagnostic_without_a_fix_needs_the_author() -> None:
    assert diagnostic().needs_author
    assert not diagnostic().is_mechanical


def test_a_rewrite_diagnostic_needs_the_author() -> None:
    assert diagnostic(fix=Fix.rewrite()).needs_author


@pytest.mark.parametrize('fix', [Fix.targeted(edit()), Fix.reflow(edit())])
def test_a_mechanical_diagnostic_does_not_need_the_author(fix: Fix) -> None:
    assert diagnostic(fix=fix).is_mechanical
    assert not diagnostic(fix=fix).needs_author


def test_an_empty_message_is_rejected() -> None:
    with pytest.raises(ValueError, match='empty message'):
        Diagnostic(rule_id='r', range=SourceRange(0, 1), message='')


def test_a_rule_needs_an_id() -> None:
    with pytest.raises(ValueError, match='needs an id'):
        RuleMetadata(rule_id='', summary='s', fix_kind=FixKind.REFLOW)


def test_rule_metadata_defaults_to_error() -> None:
    metadata = RuleMetadata(rule_id='mid-clause-break', summary='s', fix_kind=FixKind.REFLOW)
    assert metadata.default_severity is Severity.ERROR
    assert metadata.source == 'subedit'


def test_report_partitions_by_who_can_fix() -> None:
    mechanical = diagnostic('line-too-long', 0, Fix.reflow(edit()))
    authored = diagnostic('stub-fragment', 5, Fix.rewrite())
    report = Report((mechanical, authored))

    assert report.mechanical == (mechanical,)
    assert report.needing_author == (authored,)
    assert report.by_fix_kind(FixKind.REFLOW) == (mechanical,)
    assert report.by_fix_kind(FixKind.TARGETED) == ()
    assert not report.is_clean


def test_an_empty_report_is_clean() -> None:
    assert Report().is_clean


def test_merging_deduplicates_identical_findings_and_sorts_by_position() -> None:
    late = diagnostic('no-em-dash', 40)
    early = diagnostic('no-em-dash', 10)
    duplicate = diagnostic('no-em-dash', 10)

    merged = Report((late,)).merged_with(Report((duplicate, early)))

    assert len(merged.diagnostics) == 2
    assert [item.range.start for item in merged.diagnostics] == [10, 40]


def test_merging_keeps_findings_that_differ_only_by_rule() -> None:
    merged = Report((diagnostic('no-em-dash', 10),)).merged_with(Report((diagnostic('no-semicolon', 10),)))
    assert len(merged.diagnostics) == 2


def test_merging_records_every_unavailable_source_once() -> None:
    merged = Report(unavailable_sources=('vale',)).merged_with(Report(unavailable_sources=('vale', 'autocorrect')))
    assert merged.unavailable_sources == ('vale', 'autocorrect')


def test_severity_orders_by_urgency() -> None:
    assert Severity.ERROR > Severity.WARNING > Severity.SUGGESTION


def test_a_merge_keeps_each_finding_one_rule_makes_in_one_block() -> None:
    first, second = (
        Diagnostic(rule_id='unbreakable-sentence', range=SourceRange(0, 9), message=message)
        for message in ('the first sentence', 'the second sentence')
    )
    assert Report((first, second)).merged_with(Report()).diagnostics == (first, second)
    assert Report((first,)).merged_with(Report((first,))).diagnostics == (first,)
