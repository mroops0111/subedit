import pathlib

from ..domain.rules import (
    CommentTooLongRule,
    ContrastFramingRule,
    DiscouragedWordRule,
    FileHeaderCommentRule,
    HeadingNotNounPhraseRule,
    HeadingTitleCaseRule,
    HeadingWrappedInBoldRule,
    LineTooLongRule,
    LineTooShortRule,
    ListLabelNotBoldRule,
    ListLabelTitleCaseRule,
    MidClauseBreakRule,
    MidListBreakRule,
    MidSentenceColonRule,
    MissingBlankLineRule,
    MissingLeadSentenceRule,
    ParagraphLineBreakRule,
    ParenthesisStyleRule,
    PlainCommentOnPublicRule,
    SignatureRestatingTagRule,
    SubjectNotImperativeRule,
    SubjectStyleRule,
    SubjectTooLongRule,
    TableHeaderTitleCaseRule,
    UnbreakableSentenceRule,
)
from .config_sources import CONFIG_NAME, ConfigError, FormatterWidths, TomlConfigSource
from .linters import AutoCorrectLinter, ValeLinter
from .parsers import (
    JAVASCRIPT,
    JSON,
    PYTHON,
    TSX,
    TYPESCRIPT,
    YAML,
    CommitMessageParser,
    CompositeParser,
    LanguageProfile,
    MarkdownParser,
    NodeRole,
    TreeSitterParser,
)


LANGUAGES: tuple[LanguageProfile, ...] = (PYTHON, TYPESCRIPT, TSX, JAVASCRIPT, YAML, JSON)
COMMENT_PARSER = TreeSitterParser(LANGUAGES)
DEFAULT_PARSER = CompositeParser((COMMENT_PARSER, MarkdownParser(), CommitMessageParser()))

FILE_TYPES = DEFAULT_PARSER.file_types
EXTENSIONS = frozenset(extension for file_type in FILE_TYPES for extension in file_type.extensions)
VENDOR_DIRECTORIES = frozenset(directory for file_type in FILE_TYPES for directory in file_type.vendor_directories)
GENERATED_NAMES = frozenset(name for file_type in FILE_TYPES for name in file_type.generated_names)
PATH_ALIASES = {alias: canonical for file_type in FILE_TYPES for alias, canonical in file_type.aliases.items()}

LAYOUT_RULES = (MidClauseBreakRule(), LineTooLongRule())
REWRITE_RULES = (LineTooShortRule(), UnbreakableSentenceRule(), MidListBreakRule())
STRUCTURAL_RULES = (
    FileHeaderCommentRule(),
    PlainCommentOnPublicRule(LANGUAGES),
    SignatureRestatingTagRule(LANGUAGES),
    CommentTooLongRule(),
)
WORDING_RULES = (
    MidSentenceColonRule(),
    ParenthesisStyleRule(),
    DiscouragedWordRule(),
    ContrastFramingRule(),
    ListLabelTitleCaseRule(),
    ListLabelNotBoldRule(),
)
MARKDOWN_RULES = (
    ParagraphLineBreakRule(),
    HeadingWrappedInBoldRule(),
    HeadingTitleCaseRule(),
    TableHeaderTitleCaseRule(),
    MissingLeadSentenceRule(),
    HeadingNotNounPhraseRule(),
)
COMMIT_RULES = (SubjectTooLongRule(), SubjectStyleRule(), SubjectNotImperativeRule(), MissingBlankLineRule())
ALL_RULES = LAYOUT_RULES + REWRITE_RULES + STRUCTURAL_RULES + WORDING_RULES + MARKDOWN_RULES + COMMIT_RULES

DEFAULT_CONFIG_SOURCE = TomlConfigSource(
    tuple(rule.metadata for rule in ALL_RULES),
    FormatterWidths(
        {extension: language.width_settings for language in LANGUAGES for extension in language.extensions}
    ),
    file_types=FILE_TYPES,
)


def language_id_for(path: pathlib.Path) -> str | None:
    """The language id a document is read as, from the file's name or extension."""
    file_type = DEFAULT_PARSER.file_type_for(path)
    return None if file_type is None else file_type.language_id


EXTERNAL_LINTERS = (ValeLinter(aliases=PATH_ALIASES), AutoCorrectLinter(aliases=PATH_ALIASES))

__all__ = [
    'ALL_RULES',
    'COMMENT_PARSER',
    'COMMIT_RULES',
    'CONFIG_NAME',
    'DEFAULT_CONFIG_SOURCE',
    'DEFAULT_PARSER',
    'EXTENSIONS',
    'EXTERNAL_LINTERS',
    'FILE_TYPES',
    'GENERATED_NAMES',
    'JAVASCRIPT',
    'JSON',
    'LANGUAGES',
    'LAYOUT_RULES',
    'MARKDOWN_RULES',
    'PATH_ALIASES',
    'PYTHON',
    'REWRITE_RULES',
    'STRUCTURAL_RULES',
    'TSX',
    'TYPESCRIPT',
    'VENDOR_DIRECTORIES',
    'WORDING_RULES',
    'YAML',
    'AutoCorrectLinter',
    'CompositeParser',
    'ConfigError',
    'LanguageProfile',
    'MarkdownParser',
    'NodeRole',
    'TomlConfigSource',
    'TreeSitterParser',
    'ValeLinter',
    'language_id_for',
]
