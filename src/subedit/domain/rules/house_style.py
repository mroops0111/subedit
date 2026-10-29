import re
import typing

from ..models.diagnostic import Diagnostic, Fix, FixKind, RuleMetadata, Severity
from ..models.prose_unit import ProseLine, ProseUnit
from ..models.wording import is_protected, protected_spans, title_case
from ..ports.rule import Rule, RuleContext


MID_SENTENCE_COLON = RuleMetadata(
    rule_id='mid-sentence-colon',
    summary='A colon stands only in a heading, after a label, or at the end of a line leading into a list or block.',
    fix_kind=FixKind.REWRITE,
)

PARENTHESIS_STYLE = RuleMetadata(
    rule_id='parenthesis-style',
    summary='Parentheses around prose are half-width, spaced from the words outside, and flush with the words inside.',
    fix_kind=FixKind.TARGETED,
)

INCLUSION_VERB = RuleMetadata(
    rule_id='inclusion-verb',
    summary='Prose uses the verb for include that the house style prefers.',
    fix_kind=FixKind.TARGETED,
)

CONTRAST_FRAMING = RuleMetadata(
    rule_id='contrast-framing',
    summary='A sentence states what something is, rather than framing it against what it is not.',
    fix_kind=FixKind.REWRITE,
    default_severity=Severity.WARNING,
)

BULLET_LABEL_STYLE = RuleMetadata(
    rule_id='bullet-label-style',
    summary='A list item label is in Title Case, and bold wherever the text renders.',
    fix_kind=FixKind.TARGETED,
)


_COLON = re.compile(r'[:：]')
# A label is a few words with no sentence punctuation,
# though a comma may join two halves, set before the colon that opens a list item or paragraph.
_LABEL = re.compile(
    r'^(?P<open>\*\*|__)?'
    r'(?P<label>(?:`[^`]*`|[^\s*_:：.,;!?。，；！？`])(?:`[^`]*`|\.(?=\S)|[^*_:：.;!?。；！？`]){0,79}?)'
    r'(?P<close>\*\*|__)?(?P<note>\s*\([^()]*\))?(?P<colon>[:：])'
)
_MAX_LABEL_WORDS = 5
# A finite verb makes the words before a colon a clause, as in "The write is idempotent:", not a label.
_FINITE_VERBS = frozenset(
    {'is', 'are', 'was', 'were', 'be', 'has', 'have', 'had', 'does', 'do', 'did', 'can', 'will', 'must', 'should'}
)
_MAX_TAG_WORDS = 3
_MAX_BOLD_LABEL_WORDS = 10
_MAX_CJK_LABEL = 12
_PARENTHESES = re.compile(r'[(（](?P<inside>[^()（）]*)[)）]')
_CJK = re.compile(r'[぀-ヿ㐀-鿿豈-﫿]')
# No space goes between a parenthesis and the punctuation or bracket beside it.
_HUGS_A_PARENTHESIS = frozenset('.,;:!?，。、；：！？「」『』"\'[]{}<>/')
_CONTRAST = re.compile(r'不是[^，,。；;！!？?]{1,40}[，,]\s*(?:而)?是')


class MidSentenceColonRule(Rule[ProseUnit]):
    metadata = MID_SENTENCE_COLON
    surface = ProseUnit

    def check(self, unit: ProseUnit, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if unit.is_heading or unit.is_quoted:
            return
        for line in unit.prose_lines():
            spans = protected_spans(line.text)
            label_end = _label_colon(line)
            trailing = line.text.rstrip().rstrip('*_')
            for colon in _COLON.finditer(line.text):
                offset = colon.start()
                if offset == label_end or is_protected(offset, spans) or not _closes_a_clause(line.text, offset):
                    continue
                if offset >= len(trailing) - 1 and line.ends_paragraph:
                    continue
                yield Diagnostic(
                    rule_id=self.metadata.rule_id,
                    range=line.span(offset, offset + 1),
                    message=(
                        'A colon joins clauses or leads into an inline list here. '
                        'A colon belongs in a heading, after a label, or at the end of a line that a list or block follows. '
                        'Split the sentence in two, or turn the inline list into a list.'
                    ),
                    fix=Fix.rewrite(),
                )


class ParenthesisStyleRule(Rule[ProseUnit]):
    metadata = PARENTHESIS_STYLE
    surface = ProseUnit

    def check(self, unit: ProseUnit, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if unit.is_quoted:
            return
        for line in unit.prose_lines():
            spans = protected_spans(line.text)
            for parentheses in _PARENTHESES.finditer(line.text):
                start, end = parentheses.span()
                if is_protected(start, spans) or line.text[start - 1 : start] == ']':
                    continue
                inside = parentheses.group('inside')
                full_width = parentheses.group().startswith('（') or parentheses.group().endswith('）')
                # A call such as foo(bar) holds no space and no CJK text, so it is code, not an aside.
                if not full_width and not (_CJK.search(inside) or ' ' in inside):
                    continue
                before = line.text[start - 1] if start else ''
                after = line.text[end] if end < len(line.text) else ''
                styled = (
                    (' ' if before and not before.isspace() and before not in _HUGS_A_PARENTHESIS else '')
                    + f'({inside.strip()})'
                    + (' ' if after and not after.isspace() and after not in _HUGS_A_PARENTHESIS else '')
                )
                if styled == parentheses.group():
                    continue
                yield Diagnostic(
                    rule_id=self.metadata.rule_id,
                    range=line.span(start, end),
                    message=(
                        'Parentheses are half-width, with a space outside and none inside, '
                        f'so this reads as "{styled.strip()}".'
                    ),
                    fix=Fix.targeted(line.edit(start, end, styled)),
                )


class InclusionVerbRule(Rule[ProseUnit]):
    metadata = INCLUSION_VERB
    surface = ProseUnit

    def check(self, unit: ProseUnit, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if unit.is_quoted:
            return
        for line in unit.prose_lines():
            spans = protected_spans(line.text)
            for found in re.finditer('包括', line.text):
                if is_protected(found.start(), spans):
                    continue
                yield Diagnostic(
                    rule_id=self.metadata.rule_id,
                    range=line.span(*found.span()),
                    message='The house style writes 包含 rather than 包括.',
                    fix=Fix.targeted(line.edit(*found.span(), '包含')),
                )


class ContrastFramingRule(Rule[ProseUnit]):
    metadata = CONTRAST_FRAMING
    surface = ProseUnit

    def check(self, unit: ProseUnit, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if unit.is_quoted:
            return
        for line in unit.prose_lines():
            for found in _CONTRAST.finditer(line.text):
                yield Diagnostic(
                    rule_id=self.metadata.rule_id,
                    range=line.span(*found.span()),
                    message=(
                        'This sentence frames what something is against what it is not, as in 不是 A，是 B. '
                        'State B directly, or write 是 B 而非 A where the contrast matters.'
                    ),
                    fix=Fix.rewrite(),
                )


class BulletLabelStyleRule(Rule[ProseUnit]):
    metadata = BULLET_LABEL_STYLE
    surface = ProseUnit

    def check(self, unit: ProseUnit, context: RuleContext) -> typing.Iterable[Diagnostic]:
        keep = context.settings(HEADING_TITLE_CASE_ID).strings('keep')
        for line in unit.prose_lines():
            if not line.opens_item:
                continue
            label = _LABEL.match(line.text)
            if label is None or not _is_label(label.group('label')):
                continue
            opener, end = label.group('open'), label.end()
            bold = bool(opener and label.group('close'))
            # A label written as `**Label:**` closes its bold after the colon.
            if opener and not label.group('close') and line.text.startswith(opener, end):
                bold, end = True, end + len(opener)
            words = title_case(label.group('label'), keep)
            marker = '**' if bold or unit.renders_markup else ''
            styled = f'{marker}{words}{marker}{label.group("note") or ""}{label.group("colon")}'
            if styled == line.text[:end]:
                continue
            yield Diagnostic(
                rule_id=self.metadata.rule_id,
                range=line.span(0, end),
                message=f'A list item label is in Title Case, and bold where the text renders, so it reads "{styled}".',
                fix=Fix.targeted(line.edit(0, end, styled)),
            )


# Title Case and the names it leaves lowercase are set once, on the heading rule, and labels follow them.
HEADING_TITLE_CASE_ID = 'heading-title-case'


# A list item may open with any short label, while a paragraph opens with one only as a capitalized tag such as Note.
# A label the author set in bold is taken at their word, up to a longer limit.
def _label_colon(line: ProseLine) -> int | None:
    label = _LABEL.match(line.text) if line.opens_item or line.opens_paragraph else None
    if label is None:
        return None
    if label.group('open'):
        return label.start('colon') if len(label.group('label').split()) <= _MAX_BOLD_LABEL_WORDS else None
    if not _is_label(label.group('label')):
        return None
    if not line.opens_item and not _is_tag(label.group('label')):
        return None
    return label.start('colon')


def _is_label(text: str) -> bool:
    if _CJK.search(text):
        return len(text.strip()) <= _MAX_CJK_LABEL
    words = text.split()
    if any(word.lower() in _FINITE_VERBS for word in words):
        return False
    return 0 < len(words) <= _MAX_LABEL_WORDS and not text.rstrip().endswith(('http', 'https'))


def _is_tag(text: str) -> bool:
    words = text.split()
    return 0 < len(words) <= _MAX_TAG_WORDS and all(word[:1].isupper() for word in words)


# A half-width colon closes a clause only before a space or the end of the line, which leaves out a time or a scheme.
def _closes_a_clause(text: str, offset: int) -> bool:
    if text[offset] == '：':
        return True
    following = text[offset + 1 : offset + 4]
    if following.startswith(('**', '__')):
        following = following[2:]
    return not following or following[0].isspace()
