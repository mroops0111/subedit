import typing

from ..models.comment import CommentGroup, CommentPlacement
from ..models.diagnostic import Diagnostic, Fix, FixKind, RuleMetadata, Severity
from ..models.prose import Prose, reflow_sentence
from ..ports.rule import Rule, RuleContext


STUB_FRAGMENT = RuleMetadata(
    rule_id='stub-fragment',
    summary='A sentence forced to break must not leave a stub of a line behind.',
    fix_kind=FixKind.REWRITE,
    default_severity=Severity.WARNING,
)

UNBREAKABLE_SENTENCE = RuleMetadata(
    rule_id='unbreakable-sentence',
    summary=(
        'A sentence over the width must carry a clause comma, splitting no list, wherever it has to break, '
        'and a summary its style guide keeps to one line must fit it.'
    ),
    fix_kind=FixKind.REWRITE,
)


DEFAULT_MINIMUM_CHARACTERS = 24
BRACKET_NOTE = 'A comma inside brackets or a code span separates items, so it is no place to break. '


def prose_sentences(group: CommentGroup) -> tuple[str, ...]:
    return tuple(
        sentence.text
        for segment in group.prose().segments()
        if not segment.is_literal
        for sentence in Prose(segment.text, group.markup).sentences()
    )


def budgeted_sentences(group: CommentGroup, context: RuleContext) -> tuple[tuple[str, int], ...]:
    """Pair each sentence with the budget reflow lays it out in, so no rule judges a layout reflow would not make."""
    return tuple(
        (sentence, group.text_budget(context.line_width, first_line=index == 0))
        for index, sentence in enumerate(prose_sentences(group))
    )


def is_summary(group: CommentGroup, index: int) -> bool:
    """Whether a sentence is the comment's one-line summary, which reflow never breaks."""
    return index == 0 and group.has_summary_line


def stub_floor(context: RuleContext) -> int:
    """Reflow reads the same floor, so a fix never lays out a stub that this rule then rejects."""
    if not context.rule_set.is_enabled(STUB_FRAGMENT.rule_id):
        return 0
    return context.settings(STUB_FRAGMENT.rule_id).integer('minimum_characters', DEFAULT_MINIMUM_CHARACTERS)


class StubFragmentRule(Rule[CommentGroup]):
    metadata = STUB_FRAGMENT
    surface = CommentGroup

    def check(self, group: CommentGroup, context: RuleContext) -> typing.Iterable[Diagnostic]:
        # A trailing comment never breaks, so a rule judging where a sentence breaks leaves it to line-too-long.
        if group.placement is CommentPlacement.TRAILING:
            return
        minimum_length = stub_floor(context)
        for index, (sentence, budget) in enumerate(budgeted_sentences(group, context)):
            if is_summary(group, index):
                continue
            split_pieces = reflow_sentence(sentence, budget, minimum_length)
            if len(split_pieces) < 2:
                continue
            shortest_piece = min(split_pieces, key=len)
            if len(shortest_piece) >= minimum_length:
                continue
            yield Diagnostic(
                rule_id=self.metadata.rule_id,
                range=group.range,
                message=(
                    f'Breaking this sentence leaves a line of {len(shortest_piece)} characters, below the minimum of '
                    f'{minimum_length}, so the layout reads as a stub rather than a clause. '
                    f'Rewrite it to fit one line, or split it into two complete sentences. '
                    f'The fragment is "{shortest_piece.strip()}".'
                ),
                fix=Fix.rewrite(),
            )


class UnbreakableSentenceRule(Rule[CommentGroup]):
    metadata = UNBREAKABLE_SENTENCE
    surface = CommentGroup

    def check(self, group: CommentGroup, context: RuleContext) -> typing.Iterable[Diagnostic]:
        # A trailing comment never breaks, so its width is line-too-long's to judge.
        if group.placement is CommentPlacement.TRAILING:
            return
        sentences = budgeted_sentences(group, context)
        for index, (sentence, budget) in enumerate(sentences):
            if is_summary(group, index):
                # A summary with nothing after it closes on its own line, so the quotes share its budget.
                closing = len(group.closing()) if len(sentences) == 1 else 0
                message = self._summary_message(sentence, budget - closing, group.layout.summary_convention)
            else:
                message = self._sentence_message(sentence, budget)
            if message is not None:
                yield Diagnostic(rule_id=self.metadata.rule_id, range=group.range, message=message, fix=Fix.rewrite())
        for sentence in group.sentences_held_by_a_list(context.line_width, stub_floor(context)):
            yield Diagnostic(
                rule_id=self.metadata.rule_id,
                range=group.range,
                message=self._list_message(sentence),
                fix=Fix.rewrite(),
            )

    def _summary_message(self, sentence: str, budget: int, convention: str | None) -> str | None:
        if len(sentence) <= budget:
            return None
        return (
            f'This summary runs to {len(sentence)} characters against a budget of {budget} characters, '
            f'and {convention} asks that a summary fit one line, since indexing tools read only that line. '
            'Shorten it to what the object does, and move the detail into the body below it.'
        )

    def _sentence_message(self, sentence: str, budget: int) -> str | None:
        longest_line = max(reflow_sentence(sentence, budget), key=len)
        if len(longest_line) <= budget:
            return None
        if longest_line == sentence:
            cause = 'contains no comma that ends a clause, so there is no legal place to break it'
        else:
            cause = f'still leaves a line of {len(longest_line)} characters when broken at every clause comma'
        return (
            f'This sentence runs to {len(sentence)} characters against a budget of {budget} characters '
            f'and {cause}. '
            f'{BRACKET_NOTE if "," in sentence else ""}'
            'Add a comma at a clause boundary, or split it into two sentences. '
            f'The part that does not fit is "{longest_line}".'
        )

    def _list_message(self, sentence: str) -> str:
        return (
            f'This sentence breaks in mid clause, and every clause comma it could break at instead splits a list, '
            'leaving its items on two lines. '
            'Move the list to the end of the sentence, or split it into two sentences. '
            f'The sentence opens with "{" ".join(sentence.split()[:8])}".'
        )
