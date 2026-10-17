import abc
import enum

from tree_sitter import Language, Node

from ....domain.models.comment import DocFrame, SymbolKind, Visibility
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
    # A docstring has no frame and lives inside what it documents, while a JSDoc block is framed and stands above it.
    doc_frame: DocFrame | None = None
    doc_leads_declaration = False
    default_line_width = 120

    def visibility_of_declaration(self, declaration: Node, name: str) -> Visibility:
        """How visible a declaration is, read from its syntax where a language marks it there."""
        return self.visibility_of(name)
