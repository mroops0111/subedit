import abc
import enum

from tree_sitter import Language, Node

from ....domain.models.comment import SymbolKind, Visibility
from ....domain.models.comment_layout import CommentLayout
from ....domain.models.prose import PLAIN_MARKUP, ProseMarkup
from ....domain.models.rule_set import DEFAULT_LINE_WIDTH
from ....domain.ports.language_conventions import LanguageConventions


class NodeRole(enum.Enum):
    ROOT = 'root'
    DEFINITION = 'definition'
    IMPORT = 'import'
    COMMENT = 'comment'
    OTHER = 'other'


class GrammarAdapter(abc.ABC):
    # The grammar ships as a wheel, so a first run never reaches the network.
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
    default_line_width = DEFAULT_LINE_WIDTH
    # Directories a package manager fills with code nobody in the project wrote.
    vendor_directories: frozenset[str] = frozenset()

    def imports_for_effect(self, node: Node) -> bool:
        """Whether an import binds no name and runs only for its side effect, which a comment over it explains."""
        return False

    def exported_names(self, root: Node) -> frozenset[str]:
        """The names a module exports apart from where it declares them, read once per parse."""
        return frozenset()

    def visibility_of_declaration(self, declaration: Node, name: str, exported: frozenset[str]) -> Visibility:
        """How visible a declaration is, read from its syntax where a language marks it there."""
        return self.visibility_of(name)
