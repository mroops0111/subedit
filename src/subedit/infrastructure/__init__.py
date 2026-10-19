import pathlib

from ..domain.rules import (
    BlockTooLongRule,
    FileHeaderCommentRule,
    LineTooLongRule,
    MidClauseBreakRule,
    PlainCommentOnPublicRule,
    SignatureRestatingTagRule,
    StubFragmentRule,
    UnbreakableSentenceRule,
)
from .config_sources import CONFIG_NAME, TomlConfigSource
from .linters import AutoCorrectLinter, ValeLinter
from .parsers import PYTHON, TSX, TYPESCRIPT, LanguageProfile, NodeRole, TreeSitterParser


LANGUAGES: tuple[LanguageProfile, ...] = (PYTHON, TYPESCRIPT, TSX)
EXTENSIONS = frozenset(extension for language in LANGUAGES for extension in language.extensions)
VENDOR_DIRECTORIES = frozenset(directory for language in LANGUAGES for directory in language.vendor_directories)
SUFFIX_ALIASES = {
    extension: language.canonical_extension
    for language in LANGUAGES
    for extension in language.extensions
    if extension != language.canonical_extension
}

LAYOUT_RULES = (MidClauseBreakRule(), LineTooLongRule())
REWRITE_RULES = (StubFragmentRule(), UnbreakableSentenceRule())
STRUCTURAL_RULES = (
    FileHeaderCommentRule(),
    PlainCommentOnPublicRule(LANGUAGES),
    SignatureRestatingTagRule(LANGUAGES),
    BlockTooLongRule(),
)
ALL_RULES = LAYOUT_RULES + REWRITE_RULES + STRUCTURAL_RULES

DEFAULT_PARSER = TreeSitterParser(LANGUAGES)
DEFAULT_CONFIG_SOURCE = TomlConfigSource(
    tuple(rule.metadata.rule_id for rule in ALL_RULES),
    {extension: language.default_line_width for language in LANGUAGES for extension in language.extensions},
)


def language_for(path: pathlib.Path) -> LanguageProfile | None:
    """The language a file is written in, read from its extension."""
    return next((language for language in LANGUAGES if path.suffix in language.extensions), None)


EXTERNAL_LINTERS = (ValeLinter(suffix_aliases=SUFFIX_ALIASES), AutoCorrectLinter(suffix_aliases=SUFFIX_ALIASES))

__all__ = [
    'ALL_RULES',
    'CONFIG_NAME',
    'DEFAULT_CONFIG_SOURCE',
    'DEFAULT_PARSER',
    'EXTENSIONS',
    'EXTERNAL_LINTERS',
    'LANGUAGES',
    'LAYOUT_RULES',
    'PYTHON',
    'REWRITE_RULES',
    'STRUCTURAL_RULES',
    'SUFFIX_ALIASES',
    'TSX',
    'TYPESCRIPT',
    'VENDOR_DIRECTORIES',
    'AutoCorrectLinter',
    'LanguageProfile',
    'NodeRole',
    'TomlConfigSource',
    'TreeSitterParser',
    'ValeLinter',
    'language_for',
]
