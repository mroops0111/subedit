import typing

from ..models.comment import CommentGroup, CommentPlacement
from ..models.diagnostic import CountOption, Diagnostic, Fix, FixKind, RuleMetadata, Severity
from ..models.prose import Prose
from ..models.reflow import BreakPolicy, reflow_sentence
from ..ports.rule import Rule, RuleContext


_MINIMUM_CHARACTERS = CountOption('minimum-characters', 24)
# A piece this short between two commas may be a list item.
_MAX_ITEM_WORDS = CountOption('max-item-words', 3)
_BRACKET_NOTE = 'A comma inside brackets or a code span separates items, so it is no place to break. '


def is_summary(group: CommentGroup, index: int) -> bool:
    """Whether a sentence is the comment's one-line summary, which reflow never breaks."""
    return index == 0 and group.has_summary_line


def break_policy(context: RuleContext) -> BreakPolicy:
    """What reflow avoids, read from the rules that judge it, so a fix never lays out what they then reject.

    A rule switched off leaves its concern out of the layout too.
    """
    rule_set = context.rule_set
    short = LineTooShortRule.metadata.rule_id
    split = MidListBreakRule.metadata.rule_id
    return BreakPolicy(
        stub_floor=context.settings(short).value(_MINIMUM_CHARACTERS) if rule_set.is_enabled(short) else 0,
        list_item_words=context.settings(split).value(_MAX_ITEM_WORDS) if rule_set.is_enabled(split) else None,
        abbreviations=rule_set.abbreviations,
    )


class LineTooShortRule(Rule[CommentGroup]):
    metadata = RuleMetadata(
        rule_id='line-too-short',
        summary='A sentence forced to break must not leave a line too short to read as a clause.',
        fix_kind=FixKind.REWRITE,
        default_severity=Severity.WARNING,
        options=(_MINIMUM_CHARACTERS,),
    )
    surface = CommentGroup

    def check(self, group: CommentGroup, context: RuleContext) -> typing.Iterable[Diagnostic]:
        # A trailing comment never breaks, so a rule judging where a sentence breaks leaves it to line-too-long.
        if group.placement is CommentPlacement.TRAILING:
            return
        policy = break_policy(context)
        minimum_length = policy.stub_floor
        for index, (sentence, budget) in enumerate(_budgeted_sentences(group, context)):
            if is_summary(group, index):
                continue
            split_pieces = reflow_sentence(sentence, budget, policy)
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
                    f'{minimum_length}, so the short line reads as a leftover rather than a clause. '
                    f'Rewrite it to fit one line, or split it into two complete sentences. '
                    f'The fragment is "{shortest_piece.strip()}".'
                ),
                fix=Fix.rewrite(),
            )


class UnbreakableSentenceRule(Rule[CommentGroup]):
    metadata = RuleMetadata(
        rule_id='unbreakable-sentence',
        summary=(
            'A sentence over the width must carry a clause comma wherever it has to break, '
            'and a summary its style guide keeps to one line must fit it.'
        ),
        fix_kind=FixKind.REWRITE,
    )
    surface = CommentGroup

    def check(self, group: CommentGroup, context: RuleContext) -> typing.Iterable[Diagnostic]:
        # A trailing comment never breaks, so its width is line-too-long's to judge.
        if group.placement is CommentPlacement.TRAILING:
            return
        sentences = _budgeted_sentences(group, context)
        for index, (sentence, budget) in enumerate(sentences):
            if is_summary(group, index):
                # A summary with nothing after it closes on its own line, so the quotes share its budget.
                closing = len(group.closing()) if len(sentences) == 1 else 0
                message = self._summary_message(sentence, budget - closing, group.layout.summary_convention)
            else:
                message = self._sentence_message(sentence, budget)
            if message is not None:
                yield Diagnostic(rule_id=self.metadata.rule_id, range=group.range, message=message, fix=Fix.rewrite())

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
            f'{_BRACKET_NOTE if "," in sentence else ""}'
            'Add a comma at a clause boundary, or split it into two sentences. '
            f'The part that does not fit is "{longest_line}".'
        )


class MidListBreakRule(Rule[CommentGroup]):
    metadata = RuleMetadata(
        rule_id='mid-list-break',
        summary='A sentence that has to break should not break between the items of a list.',
        fix_kind=FixKind.REWRITE,
        default_severity=Severity.WARNING,
        options=(_MAX_ITEM_WORDS,),
    )
    surface = CommentGroup

    def check(self, group: CommentGroup, context: RuleContext) -> typing.Iterable[Diagnostic]:
        # Whether a comma parts list items or an aside is syntax, which only a reader can settle, so this warns.
        if group.placement is CommentPlacement.TRAILING:
            return
        for sentence in group.sentences_splitting_a_list(context.rule_set.line_width, break_policy(context)):
            yield Diagnostic(
                rule_id=self.metadata.rule_id,
                range=group.range,
                message=(
                    'This sentence seems to break between the items of a list, leaving them on two lines. '
                    'If the comma does part list items, move the list to the end of the sentence, '
                    'or split it into two sentences. If it parts an aside or a clause, leave it. '
                    f'The sentence opens with "{" ".join(sentence.split()[:8])}".'
                ),
                fix=Fix.rewrite(),
            )


def _prose_sentences(group: CommentGroup, context: RuleContext) -> tuple[str, ...]:
    return tuple(
        sentence.text
        for segment in group.prose().segments()
        if not segment.is_literal
        for sentence in Prose(segment.text, group.markup).sentences(context.rule_set.abbreviations)
    )


def _budgeted_sentences(group: CommentGroup, context: RuleContext) -> tuple[tuple[str, int], ...]:
    """Pair each sentence with the budget reflow lays it out in, so no rule judges a layout reflow would not make."""
    return tuple(
        (sentence, group.text_budget(context.rule_set.line_width, first_line=index == 0))
        for index, sentence in enumerate(_prose_sentences(group, context))
    )
