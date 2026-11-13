import re
import typing

from ..models.commit_message import CommitSubject
from ..models.diagnostic import Diagnostic, Fix, FixKind, RuleMetadata, Severity
from ..models.measurement import Measurement
from ..models.position import SourceRange
from ..models.rule_option import ChoiceOption, CountOption, WordsOption
from ..models.text import TextEdit
from ..ports.rule import MeasuredRule, Rule, RuleContext


# The types @commitlint/config-conventional allows, which most projects on Conventional Commits take.
CONVENTIONAL_TYPES = ('build', 'chore', 'ci', 'docs', 'feat', 'fix', 'perf', 'refactor', 'revert', 'style', 'test')

# GitHub shortens a longer subject, and git's own documentation keeps it to this.
_MAX_SUBJECT_CHARACTERS = CountOption('max-subject-characters', 72)
_GIT, _CONVENTIONAL = 'git', 'conventional'
# git's own convention capitalizes the description, and Conventional Commits puts a type before it in lowercase.
_STYLE = ChoiceOption('style', _GIT, choices=(_GIT, _CONVENTIONAL))
_TYPES = WordsOption('types', CONVENTIONAL_TYPES)

_TYPE = re.compile(r'^(?P<type>[\w-]+)(?:\([^)]*\))?!?: $')
_FIRST_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
# Verbs whose base form already ends as a past tense or a third person form would.
_BASE_FORMS = frozenset({'embed', 'feed', 'need', 'proceed', 'seed', 'shed', 'speed', 'succeed', 'exceed', 'focus'})


class SubjectTooLongRule(MeasuredRule[CommitSubject]):
    metadata = RuleMetadata(
        rule_id='subject-too-long',
        summary='A commit subject fits the width git log and GitHub show it in.',
        fix_kind=FixKind.REWRITE,
        options=(_MAX_SUBJECT_CHARACTERS,),
    )
    surface = CommitSubject

    def check(self, unit: CommitSubject, context: RuleContext) -> typing.Iterable[Diagnostic]:
        limit = context.settings(self.metadata.rule_id).value(_MAX_SUBJECT_CHARACTERS)
        if len(unit.text) <= limit:
            return
        yield Diagnostic(
            rule_id=self.metadata.rule_id,
            range=unit.range,
            message=(
                f'This subject runs to {len(unit.text)} characters against a limit of {limit}, '
                'and GitHub and git log --oneline cut a longer one short. '
                'Keep what the change does, and move why and how into the body.'
            ),
            fix=Fix.rewrite(),
        )

    def measure(self, unit: CommitSubject, context: RuleContext) -> typing.Iterable[Measurement]:
        yield Measurement(_MAX_SUBJECT_CHARACTERS, len(unit.text))


class SubjectStyleRule(Rule[CommitSubject]):
    metadata = RuleMetadata(
        rule_id='subject-style',
        summary='A commit subject follows the project convention, git or Conventional Commits, and ends with no period.',
        fix_kind=FixKind.TARGETED,
        options=(_STYLE, _TYPES),
    )
    surface = CommitSubject

    def check(self, unit: CommitSubject, context: RuleContext) -> typing.Iterable[Diagnostic]:
        settings = context.settings(self.metadata.rule_id)
        description = unit.description
        if description.rstrip().endswith('.') and not description.rstrip().endswith('..'):
            yield self._finding(
                unit,
                'A subject is a title, so it ends with no period.',
                description.rstrip()[:-1] + description[len(description.rstrip()) :],
            )
        if settings.value(_STYLE) == _CONVENTIONAL:
            yield from self._conventional(unit, settings.value(_TYPES))
        elif not unit.prefix and description[:1].islower() and not _is_a_name(description):
            yield self._finding(
                unit, 'Under git convention a subject opens with a capital.', description[:1].upper() + description[1:]
            )

    def _conventional(self, unit: CommitSubject, types: tuple[str, ...]) -> typing.Iterator[Diagnostic]:
        declared = _TYPE.match(unit.prefix)
        if declared is None or declared.group('type') not in types:
            written = f'{declared.group("type")}: ' if declared else 'no type'
            yield Diagnostic(
                rule_id=self.metadata.rule_id,
                range=unit.range,
                message=(
                    f'Under Conventional Commits a subject opens with a type, one of {", ".join(types)}, '
                    f'but this one has {written.strip()}. Name the kind of change, as in fix: handle empty input.'
                ),
                fix=Fix.rewrite(),
            )
            return
        description = unit.description
        if description[:1].isupper() and not _is_a_name(description):
            yield self._finding(
                unit,
                'Under Conventional Commits the description after the type opens in lowercase.',
                description[:1].lower() + description[1:],
            )

    def _finding(self, unit: CommitSubject, reason: str, description: str) -> Diagnostic:
        return Diagnostic(
            rule_id=self.metadata.rule_id,
            range=unit.range,
            message=f'{reason} It reads "{unit.prefix}{description}".',
            fix=Fix.targeted(unit.as_edit(description)),
        )


class SubjectNotImperativeRule(Rule[CommitSubject]):
    metadata = RuleMetadata(
        rule_id='subject-not-imperative',
        summary='A commit subject says what the change does, as an instruction such as Fix, not Fixed or Fixes.',
        fix_kind=FixKind.REWRITE,
        default_severity=Severity.WARNING,
    )
    surface = CommitSubject

    def check(self, unit: CommitSubject, context: RuleContext) -> typing.Iterable[Diagnostic]:
        word = _FIRST_WORD.match(unit.description)
        if word is None or not _reads_as_no_instruction(word.group()):
            return
        # Whether a word is a verb at all is grammar a word list can only guess, so this is advice.
        yield Diagnostic(
            rule_id=self.metadata.rule_id,
            range=unit.range,
            message=(
                f'{word.group()} reports the change rather than giving it as an instruction, '
                'which git and Conventional Commits both ask for, as in Fix rather than Fixed or Fixes. '
                'Leave it if the word is no verb.'
            ),
            fix=Fix.rewrite(),
            tentative=True,
        )


class SubjectRunsIntoBodyRule(Rule[CommitSubject]):
    metadata = RuleMetadata(
        rule_id='subject-runs-into-body',
        summary='A blank line parts a commit subject from its body, since git reads every line before it as the subject.',
        fix_kind=FixKind.TARGETED,
    )
    surface = CommitSubject

    def check(self, unit: CommitSubject, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if not unit.runs_into_body:
            return
        yield Diagnostic(
            rule_id=self.metadata.rule_id,
            range=unit.range,
            message='git reads every line up to the first blank one as the subject, so a blank line goes under it.',
            fix=Fix.targeted(TextEdit(SourceRange(unit.range.end, unit.range.end), '\n')),
        )


# A word with a capital after its first letter, such as iOS or OAuth, is a name that keeps its case.
def _is_a_name(description: str) -> bool:
    word = description.split(' ', 1)[0]
    return any(character.isupper() for character in word[1:])


def _reads_as_no_instruction(word: str) -> bool:
    lowered = word.lower()
    if lowered in _BASE_FORMS or len(lowered) < 4:
        return False
    if lowered.endswith('ing'):
        return any(vowel in lowered[:-3] for vowel in 'aeiouy')
    if lowered.endswith('ed'):
        return True
    return lowered.endswith('s') and not lowered.endswith(('ss', 'us', 'is'))
