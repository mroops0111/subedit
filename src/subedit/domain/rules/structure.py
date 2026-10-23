import re
import typing

from ..models.comment import CommentForm, CommentGroup, CommentPlacement
from ..models.diagnostic import Diagnostic, Fix, FixKind, RuleMetadata, Severity
from ..ports.language_conventions import LanguageConventions
from ..ports.rule import Rule, RuleContext


FILE_HEADER_COMMENT = RuleMetadata(
    rule_id='file-header-comment',
    summary='A file must not open with a banner comment before its first declaration.',
    fix_kind=FixKind.REWRITE,
    default_severity=Severity.WARNING,
)

PLAIN_COMMENT_ON_PUBLIC = RuleMetadata(
    rule_id='plain-comment-on-public',
    summary='A public symbol must be documented in the doc comment form its language renders.',
    fix_kind=FixKind.REWRITE,
)

SIGNATURE_RESTATING_TAG = RuleMetadata(
    rule_id='signature-restating-tag',
    summary='A doc comment must not restate what the type signature already carries.',
    fix_kind=FixKind.REWRITE,
)


class FileHeaderCommentRule(Rule[CommentGroup]):
    metadata = FILE_HEADER_COMMENT
    surface = CommentGroup

    def check(self, group: CommentGroup, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if group.placement is not CommentPlacement.FILE_HEADER:
            return
        yield Diagnostic(
            rule_id=self.metadata.rule_id,
            range=group.range,
            message=(
                'This comment opens the file before any declaration. '
                'A reader has the file, not a banner about it, so delete it. '
                'If it states a constraint, move that to the declaration the constraint applies to.'
            ),
            fix=Fix.rewrite(),
        )


class ConventionsByLanguage:
    """Each language spells its doc comment and its tags its own way, so a rule asks per document."""

    def __init__(self, conventions: tuple[LanguageConventions, ...]) -> None:
        self._by_language = {language.language_id: language for language in conventions}

    def lookup(self, context: RuleContext) -> LanguageConventions | None:
        return self._by_language.get(context.document.language_id)


class PlainCommentOnPublicRule(Rule[CommentGroup]):
    metadata = PLAIN_COMMENT_ON_PUBLIC
    surface = CommentGroup

    def __init__(self, conventions: tuple[LanguageConventions, ...]) -> None:
        self._conventions = ConventionsByLanguage(conventions)

    def check(self, group: CommentGroup, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if not group.attaches_to_public_symbol or group.form is CommentForm.DOC:
            return
        if group.placement is not CommentPlacement.LEADING_DECLARATION:
            return
        conventions = self._conventions.lookup(context)
        if conventions is None:
            return
        delimiter = conventions.doc_delimiter
        attachment = group.attachment
        name = attachment.name if attachment else 'the symbol'
        message = (
            f'{name} is public but documented with a plain comment. '
            f'Move the text into a {delimiter} doc comment so tooling renders it on hover.'
        )
        may_head_a_group = attachment is not None and attachment.may_head_a_group
        if may_head_a_group:
            message += (
                f' If it heads the declarations below it as a group rather than describing {name}, leave it, '
                'or set it apart with a blank line above it.'
            )
        yield Diagnostic(
            rule_id=self.metadata.rule_id,
            range=group.range,
            message=message,
            fix=Fix.rewrite(),
            tentative=may_head_a_group,
        )


class SignatureRestatingTagRule(Rule[CommentGroup]):
    metadata = SIGNATURE_RESTATING_TAG
    surface = CommentGroup

    def __init__(self, conventions: tuple[LanguageConventions, ...]) -> None:
        self._conventions = ConventionsByLanguage(conventions)

    def check(self, group: CommentGroup, context: RuleContext) -> typing.Iterable[Diagnostic]:
        conventions = self._conventions.lookup(context)
        if group.form is not CommentForm.DOC or conventions is None:
            return
        for line in group.lines:
            matched_tag = self._first_matching_tag(line.text, conventions.signature_tags)
            if matched_tag is None:
                continue
            yield Diagnostic(
                rule_id=self.metadata.rule_id,
                range=group.range,
                message=(
                    f'The tag "{matched_tag}" restates the signature, which the annotations already carry. '
                    'Delete the tag and its block. '
                    'If a parameter needs explaining, say why it matters in prose instead.'
                ),
                fix=Fix.rewrite(),
            )
            return

    # A tag matches only as a whole word, so a short tag never claims a longer one that opens with it.
    def _first_matching_tag(self, text: str, signature_tags: tuple[str, ...]) -> str | None:
        stripped_text = text.strip()
        for matched_tag in signature_tags:
            if re.match(re.escape(matched_tag) + r'(?![\w-])', stripped_text):
                return matched_tag
        return None


BLOCK_TOO_LONG = RuleMetadata(
    rule_id='block-too-long',
    summary='A comment block long enough to restate the code has stopped earning its place.',
    fix_kind=FixKind.REWRITE,
    default_severity=Severity.WARNING,
)


# Set from the p95 of a measured corpus, which subedit stats reports.
# A comment past this length has usually started restating the code below it.
DEFAULT_LIMITS = {
    'line': 4,
    'doc-internal': 13,
    'doc-public': 20,
}


class BlockTooLongRule(Rule[CommentGroup]):
    metadata = BLOCK_TOO_LONG
    surface = CommentGroup

    def check(self, group: CommentGroup, context: RuleContext) -> typing.Iterable[Diagnostic]:
        category = self._category(group)
        limit = context.settings(self.metadata.rule_id).integer(category, DEFAULT_LIMITS[category])
        if group.line_count <= limit:
            return
        yield Diagnostic(
            rule_id=self.metadata.rule_id,
            range=group.range,
            message=(
                f'This comment runs to {group.line_count} lines against a limit of {limit} lines for {category} '
                'comments. A comment earns its place by stating one constraint the code cannot show. '
                'Cut it to that constraint, or move the explanation into a name.'
            ),
            fix=Fix.rewrite(),
        )

    def _category(self, group: CommentGroup) -> str:
        if group.form is not CommentForm.DOC:
            return 'line'
        return 'doc-public' if group.attaches_to_public_symbol else 'doc-internal'
