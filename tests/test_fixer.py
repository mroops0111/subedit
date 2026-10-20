import pytest

from subedit.application import Fixer, Linter, RuleEngine
from subedit.domain import (
    CommentGroup,
    Diagnostic,
    Document,
    ExternalLinter,
    Fix,
    FixKind,
    Rule,
    RuleContext,
    RuleMetadata,
    RuleSet,
    SourceParser,
    SourceRange,
    TextEdit,
)
from subedit.infrastructure import ALL_RULES, DEFAULT_PARSER


LAYOUT = frozenset({'mid-clause-break', 'line-too-long', 'stub-fragment', 'unbreakable-sentence'})


def fixer(rules=ALL_RULES, max_rounds: int = 10) -> Fixer:
    return Fixer(Linter(DEFAULT_PARSER, RuleEngine(rules)), max_rounds=max_rounds)


def run(source: str, width: int = 60, enabled_rule_ids: frozenset[str] = LAYOUT, **kwargs):
    document = Document(uri='file:///a.py', text=source, language_id='python')
    return fixer(**kwargs).run(document, RuleSet(enabled_rule_ids=enabled_rule_ids, line_width=width))


def test_clean_input_is_left_alone() -> None:
    source = 'def f():\n    # short and fine.\n    pass\n'
    outcome = run(source)
    assert outcome.document.text == source
    assert not outcome.has_changes
    assert outcome.round_count == 0


def test_a_mis_wrapped_block_is_repaired() -> None:
    source = (
        'def f():\n    # cap the size so the mmap does not\n    # blow past it, an unbounded value faults.\n    pass\n'
    )
    outcome = run(source)
    assert outcome.has_changes
    assert '# cap the size so the mmap does not blow past it,\n' in outcome.document.text


def test_fixing_reaches_a_fixpoint() -> None:
    source = 'def f():\n    # one. two. three. four.\n    pass\n'
    outcome = run(source)
    assert run(outcome.document.text).document.text == outcome.document.text


def test_the_round_cap_is_honoured() -> None:
    source = 'def f():\n    # one. two. three.\n    pass\n'
    assert run(source, max_rounds=1).round_count <= 1


def test_rewrite_findings_survive_fixing_and_are_reported() -> None:
    source = (
        'def f():\n    # this single sentence has no comma anywhere and runs well past the budget here.\n    pass\n'
    )
    outcome = run(source, width=50)
    assert [item.rule_id for item in outcome.unresolved_findings] == ['unbreakable-sentence']
    assert outcome.document.text == source


def test_a_rewrite_never_contributes_an_edit() -> None:
    source = (
        'def f():\n    # this single sentence has no comma anywhere and runs well past the budget here.\n    pass\n'
    )
    outcome = run(source, width=50)
    assert outcome.applied_edit_count == 0


def test_the_document_version_advances_with_each_applied_round() -> None:
    source = (
        'def f():\n    # cap the size so the mmap does not\n    # blow past it, an unbounded value faults.\n    pass\n'
    )
    outcome = run(source)
    assert outcome.document.version == outcome.round_count


def test_targeted_edits_run_before_reflow() -> None:
    order: list[str] = []

    class TargetedRule(Rule):
        metadata = RuleMetadata(rule_id='targeted', summary='t', fix_kind=FixKind.TARGETED)

        def check(self, group: CommentGroup, context: RuleContext):
            order.append('targeted')
            if '!' in group.render():
                return
            start = group.lines[0].range.start + len(group.lines[0].indent + group.lines[0].delimiter)
            yield Diagnostic(
                rule_id='targeted',
                range=group.range,
                message='insert a delimiter',
                fix=Fix.targeted(TextEdit(SourceRange(start, start), '!')),
            )

    class ReflowRule(Rule):
        metadata = RuleMetadata(rule_id='reflowing', summary='r', fix_kind=FixKind.REFLOW)

        def check(self, group: CommentGroup, context: RuleContext):
            order.append('reflow')
            reflowed = group.reflow(context.line_width)
            if reflowed.render() != group.render():
                yield Diagnostic(
                    rule_id='reflowing',
                    range=group.range,
                    message='reflow',
                    fix=Fix.reflow(reflowed.as_edit()),
                )

    source = 'def f():\n    # one\n    # two.\n    pass\n'
    document = Document(uri='file:///a.py', text=source, language_id='python')
    outcome = Fixer(Linter(DEFAULT_PARSER, RuleEngine((ReflowRule(), TargetedRule())))).run(
        document, RuleSet(enabled_rule_ids=frozenset({'targeted', 'reflowing'}), line_width=60)
    )
    assert '!' in outcome.document.text
    assert outcome.document.text.count('    # ') == 1


def test_overlapping_edits_are_deferred_rather_than_dropped() -> None:
    class DoubleRule(Rule):
        metadata = RuleMetadata(rule_id='double', summary='d', fix_kind=FixKind.TARGETED)

        def check(self, group: CommentGroup, context: RuleContext):
            if group.render().count('!') >= 2:
                return
            start = group.range.start
            yield Diagnostic(
                rule_id='double',
                range=group.range,
                message='first',
                fix=Fix.targeted(TextEdit(SourceRange(start, start), '!')),
            )
            yield Diagnostic(
                rule_id='double',
                range=group.range,
                message='second',
                fix=Fix.targeted(TextEdit(SourceRange(start, start + 1), '!x')),
            )

    document = Document(uri='file:///a.py', text='# note\n', language_id='python')
    outcome = Fixer(Linter(DEFAULT_PARSER, RuleEngine((DoubleRule(),))), max_rounds=3).run(
        document, RuleSet(enabled_rule_ids=frozenset({'double'}), line_width=60)
    )
    assert outcome.round_count >= 1
    assert outcome.applied_edit_count >= 1


@pytest.mark.parametrize('width', [40, 60, 80, 120])
def test_fixing_is_idempotent_at_every_width(width: int) -> None:
    source = 'def f():\n    # cap the size, an unbounded value faults the runner. retry later if it fails.\n    pass\n'
    once = run(source, width=width).document.text
    assert run(once, width=width).document.text == once


class SilentParser(SourceParser):
    def supports(self, language_id: str) -> bool:
        return True

    def parse(self, document: Document) -> tuple[CommentGroup, ...]:
        return ()


class ShoutingLinter(ExternalLinter):
    """Lowercases the first SHOUT it finds, one per run, like a tool that fixes what it reports."""

    name = 'shouting'

    def __init__(self) -> None:
        self.seen: list[str] = []

    def is_available(self) -> bool:
        return True

    def run(self, document: Document) -> tuple[Diagnostic, ...]:
        self.seen.append(document.text)
        start = document.text.find('SHOUT')
        if start < 0:
            return ()
        edit = TextEdit(SourceRange(start, start + len('SHOUT')), 'shout')
        return (Diagnostic(rule_id='shouting', range=edit.range, message='lower it', fix=Fix.targeted(edit)),)


def test_external_linter_edits_are_applied_until_none_remain() -> None:
    linter = ShoutingLinter()
    document = Document(uri='file:///a.py', text='# SHOUT once\n# SHOUT twice\n', language_id='python')
    # The real parser finds the comment lines, which are the only place an external edit may land.
    result = Fixer(Linter(DEFAULT_PARSER, RuleEngine(())), (linter,)).run(document, RuleSet(frozenset()))

    assert result.document.text == '# shout once\n# shout twice\n'
    assert result.report.is_clean
    assert linter.seen[-1] == result.document.text, 'each round must lint the text as it stands, not the original'


def test_without_external_linters_their_findings_never_appear() -> None:
    document = Document(uri='file:///a.py', text='# SHOUT\n', language_id='python')
    result = Fixer(Linter(SilentParser(), RuleEngine(()))).run(document, RuleSet(frozenset()))
    assert result.document.text == '# SHOUT\n'


def test_a_docstring_whose_text_joins_onto_one_line_closes_on_that_line() -> None:
    source = 'def f():\n    """Yield each parameter,\n    skipping repeats.\n    """\n'
    assert run(source, width=120).document.text == 'def f():\n    """Yield each parameter, skipping repeats."""\n'


def test_a_one_line_docstring_that_fits_is_left_alone() -> None:
    source = 'def f():\n    """Release the resources. Default is a no-op."""\n'
    assert run(source, width=120).document.text == source


def test_a_summary_sentence_is_followed_by_a_blank_line() -> None:
    source = 'def f():\n    """Release the resources. Default is a no-op,\n    and callers may skip it.\n    """\n'
    expected = 'def f():\n    """Release the resources.\n\n    Default is a no-op, and callers may skip it.\n    """\n'
    assert run(source, width=120).document.text == expected


def test_a_sentence_whose_split_strands_a_stub_keeps_the_author_layout() -> None:
    source = (
        'class C:\n'
        '    """Settings.\n\n'
        '    ``token``, ``issuer`` and the fields under ``upstream`` accept ``${ENV_VAR}``\n'
        '    and ``${ENV_VAR:-default}`` substitution at resolve time and nowhere else.\n'
        '    """\n'
    )
    outcome = run(source, width=80)
    assert outcome.document.text == source, 'a fix must not lay out a stub its own check rejects'
    # Past the stub, the rest of the sentence has no clause comma left to break at either.
    assert [item.rule_id for item in outcome.report.needing_author] == ['stub-fragment', 'unbreakable-sentence']
