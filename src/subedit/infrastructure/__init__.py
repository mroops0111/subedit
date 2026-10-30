import pathlib

from ..domain.rules import (
    BlockTooLongRule,
    BulletLabelStyleRule,
    ContrastFramingRule,
    FileHeaderCommentRule,
    HeadingNotNounPhraseRule,
    HeadingTitleCaseRule,
    HeadingWrappedInBoldRule,
    InclusionVerbRule,
    LineTooLongRule,
    MidClauseBreakRule,
    MidSentenceColonRule,
    MissingLeadSentenceRule,
    ParagraphLineBreakRule,
    ParenthesisStyleRule,
    PlainCommentOnPublicRule,
    SignatureRestatingTagRule,
    StubFragmentRule,
    UnbreakableSentenceRule,
)
from .config_sources import CONFIG_NAME, FormatterWidths, TomlConfigSource
from .linters import AutoCorrectLinter, ValeLinter
from .parsers import (
    JAVASCRIPT,
    JSON,
    PYTHON,
    TSX,
    TYPESCRIPT,
    YAML,
    CompositeParser,
    LanguageProfile,
    MarkdownParser,
    NodeRole,
    TreeSitterParser,
)


LANGUAGES: tuple[LanguageProfile, ...] = (PYTHON, TYPESCRIPT, TSX, JAVASCRIPT, YAML, JSON)
COMMENT_PARSER = TreeSitterParser(LANGUAGES)
DEFAULT_PARSER = CompositeParser((COMMENT_PARSER, MarkdownParser()))

FILE_TYPES = DEFAULT_PARSER.file_types
EXTENSIONS = frozenset(extension for file_type in FILE_TYPES for extension in file_type.extensions)
VENDOR_DIRECTORIES = frozenset(directory for file_type in FILE_TYPES for directory in file_type.vendor_directories)
SUFFIX_ALIASES = {alias: canonical for file_type in FILE_TYPES for alias, canonical in file_type.aliases.items()}

LAYOUT_RULES = (MidClauseBreakRule(), LineTooLongRule())
REWRITE_RULES = (StubFragmentRule(), UnbreakableSentenceRule())
STRUCTURAL_RULES = (
    FileHeaderCommentRule(),
    PlainCommentOnPublicRule(LANGUAGES),
    SignatureRestatingTagRule(LANGUAGES),
    BlockTooLongRule(),
)
WORDING_RULES = (
    MidSentenceColonRule(),
    ParenthesisStyleRule(),
    InclusionVerbRule(),
    ContrastFramingRule(),
    BulletLabelStyleRule(),
)
MARKDOWN_RULES = (
    ParagraphLineBreakRule(),
    HeadingWrappedInBoldRule(),
    HeadingTitleCaseRule(),
    MissingLeadSentenceRule(),
    HeadingNotNounPhraseRule(),
)
ALL_RULES = LAYOUT_RULES + REWRITE_RULES + STRUCTURAL_RULES + WORDING_RULES + MARKDOWN_RULES

DEFAULT_CONFIG_SOURCE = TomlConfigSource(
    tuple(rule.metadata.rule_id for rule in ALL_RULES),
    FormatterWidths(
        {extension: language.width_settings for language in LANGUAGES for extension in language.extensions}
    ),
)


def language_id_for(path: pathlib.Path) -> str | None:
    """The language id a document is read as, from the file's extension."""
    return DEFAULT_PARSER.language_id_for(path.suffix)


EXTERNAL_LINTERS = (ValeLinter(suffix_aliases=SUFFIX_ALIASES), AutoCorrectLinter(suffix_aliases=SUFFIX_ALIASES))

__all__ = [
    'ALL_RULES',
    'COMMENT_PARSER',
    'CONFIG_NAME',
    'DEFAULT_CONFIG_SOURCE',
    'DEFAULT_PARSER',
    'EXTENSIONS',
    'EXTERNAL_LINTERS',
    'FILE_TYPES',
    'JAVASCRIPT',
    'JSON',
    'LANGUAGES',
    'LAYOUT_RULES',
    'MARKDOWN_RULES',
    'PYTHON',
    'REWRITE_RULES',
    'STRUCTURAL_RULES',
    'SUFFIX_ALIASES',
    'TSX',
    'TYPESCRIPT',
    'VENDOR_DIRECTORIES',
    'WORDING_RULES',
    'YAML',
    'AutoCorrectLinter',
    'CompositeParser',
    'LanguageProfile',
    'MarkdownParser',
    'NodeRole',
    'TomlConfigSource',
    'TreeSitterParser',
    'ValeLinter',
    'language_id_for',
]
