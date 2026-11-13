from subedit.domain import Baseline, SourceRange


def test_text_equal_to_its_baseline_changes_nothing() -> None:
    assert Baseline('one\ntwo\n').changed_ranges('one\ntwo\n') == ()


def test_an_added_line_is_changed() -> None:
    assert Baseline('one\nthree\n').changed_ranges('one\ntwo\nthree\n') == (SourceRange(4, 8),)


def test_a_removed_line_marks_the_lines_on_either_side() -> None:
    assert Baseline('one\ntwo\nthree\n').changed_ranges('one\nthree\n') == (SourceRange(0, 4), SourceRange(4, 10))


def test_an_empty_baseline_makes_every_line_new() -> None:
    assert Baseline('').changed_ranges('one\ntwo\n') == (SourceRange(0, 4), SourceRange(4, 8))


def test_ranges_count_bytes_in_utf_8() -> None:
    assert Baseline('café\nend\n').changed_ranges('café\nfin\n') == (SourceRange(6, 10),)
