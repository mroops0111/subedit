import abc
import enum
import re

from tree_sitter import Language, Node

from ....domain.models.comment import SymbolKind, Visibility
from ....domain.models.comment_layout import CommentLayout
from ....domain.models.file_type import FileType
from ....domain.models.prose import PLAIN_MARKUP, ProseMarkup
from ....domain.ports.language_conventions import LanguageConventions
from ...config_sources.formatter_width import WidthSetting


class NodeRole(enum.Enum):
    """What a grammar node is to the parser, which reads only definitions, imports, and comments by name."""

    ROOT = 'root'
    DEFINITION = 'definition'
    IMPORT = 'import'
    COMMENT = 'comment'
    OTHER = 'other'


class GrammarAdapter(abc.ABC):
    """What the parser needs from a language's tree-sitter grammar, which ships as a wheel so no run downloads it."""

    @abc.abstractmethod
    def language(self) -> Language: ...

    @abc.abstractmethod
    def query(self) -> str: ...

    @abc.abstractmethod
    def role_of(self, node_type: str) -> NodeRole: ...

    @abc.abstractmethod
    def symbol_kind(self, node_type: str) -> SymbolKind: ...


class LanguageProfile(LanguageConventions, GrammarAdapter):
    """Everything subedit knows about one language, so supporting another means writing a profile and nothing else."""

    doc_layout: CommentLayout
    # The extension Vale and AutoCorrect know the language by, since they read an unknown one as plain text.
    canonical_extension: str
    doc_markup: ProseMarkup = PLAIN_MARKUP
    line_markup: ProseMarkup = PLAIN_MARKUP
    # A docstring lives inside what it documents, while a JSDoc block stands above it.
    doc_leads_declaration = False
    # Where the language's formatters set a line width, which subedit follows over a default of its own.
    width_settings: tuple[WidthSetting, ...] = ()
    # Directories a package manager fills with code nobody in the project wrote.
    vendor_directories: frozenset[str] = frozenset()
    # A comment a tool reads, such as eslint-disable or noqa, which the query sets apart from prose.
    directive: re.Pattern[str] | None = None

    @property
    def file_type(self) -> FileType:
        return FileType(self.language_id, self.extensions, self.canonical_extension, self.vendor_directories)

    def is_directive(self, node: Node) -> bool:
        return self.directive is not None and bool(self.directive.match((node.text or b'').decode('utf-8')))

    def imports_for_effect(self, node: Node) -> bool:
        """Whether an import binds no name and runs only for its side effect, which a comment over it explains."""
        return False

    def exported_names(self, root: Node) -> frozenset[str]:
        """The names a module exports apart from where it declares them, read once per parse."""
        return frozenset()

    def visibility_of_declaration(self, declaration: Node, name: str, exported: frozenset[str]) -> Visibility:
        """How visible a declaration is, read from its syntax where a language marks it there."""
        return self.visibility_of(name)
