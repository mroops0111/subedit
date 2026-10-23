import pathlib

from ..domain.rules import (
    BlockTooLongRule,
    FileHeaderCommentRule,
    HeadingWrappedInBoldRule,
    LineTooLongRule,
    MidClauseBreakRule,
    ParagraphLineBreakRule,
    PlainCommentOnPublicRule,
    SignatureRestatingTagRule,
    StubFragmentRule,
    UnbreakableSentenceRule,
)
from .config_sources import CONFIG_NAME, FormatterWidths, TomlConfigSource
from .linters import AutoCorrectLinter, ValeLinter
from .parsers import (
    MARKDOWN_EXTENSIONS,
    PYTHON,
    TSX,
    TYPESCRIPT,
    CompositeParser,
    LanguageProfile,
    MarkdownParser,
    NodeRole,
    TreeSitterParser,
)


LANGUAGES: tuple[LanguageProfile, ...] = (PYTHON, TYPESCRIPT, TSX)
MARKDOWN = MarkdownParser()
EXTENSIONS = frozenset(extension for language in LANGUAGES for extension in language.extensions) | MARKDOWN_EXTENSIONS
VENDOR_DIRECTORIES = frozenset(directory for language in LANGUAGES for directory in language.vendor_directories)
SUFFIX_ALIASES = {
    extension: language.canonical_extension
    for language in LANGUAGES
    for extension in language.extensions
    if extension != language.canonical_extension
} | {'.markdown': '.md'}

LAYOUT_RULES = (MidClauseBreakRule(), LineTooLongRule())
REWRITE_RULES = (StubFragmentRule(), UnbreakableSentenceRule())
STRUCTURAL_RULES = (
    FileHeaderCommentRule(),
    PlainCommentOnPublicRule(LANGUAGES),
    SignatureRestatingTagRule(LANGUAGES),
    BlockTooLongRule(),
)
MARKDOWN_RULES = (ParagraphLineBreakRule(), HeadingWrappedInBoldRule())
ALL_RULES = LAYOUT_RULES + REWRITE_RULES + STRUCTURAL_RULES + MARKDOWN_RULES

COMMENT_PARSER = TreeSitterParser(LANGUAGES)
DEFAULT_PARSER = CompositeParser((COMMENT_PARSER, MARKDOWN))
DEFAULT_CONFIG_SOURCE = TomlConfigSource(
    tuple(rule.metadata.rule_id for rule in ALL_RULES),
    FormatterWidths(
        {extension: language.width_settings for language in LANGUAGES for extension in language.extensions}
    ),
)


def language_for(path: pathlib.Path) -> LanguageProfile | None:
    """The language a file is written in, read from its extension."""
    return next((language for language in LANGUAGES if path.suffix in language.extensions), None)


def language_id_for(path: pathlib.Path) -> str | None:
    """The language id a document is read as, a code language's or Markdown's, from the file's extension."""
    if path.suffix in MARKDOWN_EXTENSIONS:
        return MARKDOWN.language_id
    language = language_for(path)
    return language.language_id if language else None


EXTERNAL_LINTERS = (ValeLinter(suffix_aliases=SUFFIX_ALIASES), AutoCorrectLinter(suffix_aliases=SUFFIX_ALIASES))

__all__ = [
    'ALL_RULES',
    'COMMENT_PARSER',
    'CONFIG_NAME',
    'DEFAULT_CONFIG_SOURCE',
    'DEFAULT_PARSER',
    'EXTENSIONS',
    'EXTERNAL_LINTERS',
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
    'AutoCorrectLinter',
    'CompositeParser',
    'LanguageProfile',
    'MarkdownParser',
    'NodeRole',
    'TomlConfigSource',
    'TreeSitterParser',
    'ValeLinter',
    'language_for',
    'language_id_for',
]
