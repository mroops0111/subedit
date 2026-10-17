import re

import tree_sitter_typescript
from tree_sitter import Language, Node

from ....domain.models.comment import CommentForm, DocFrame, SymbolKind, Visibility
from ....domain.ports.language_conventions import DelimiterSplit
from .language_profile import LanguageProfile, NodeRole


_LINE_DELIMITER = re.compile(r'^(//+\s?)')
_DOC_OPENING = re.compile(r'^(/\*\*\s?)')
_DOC_PREFIX = re.compile(r'^(\*(?!/)\s?)')
_DOC_CLOSING = '*/'

# A plain /* */ block is usually a license header or a lint directive, so only // and /** */ are prose.
# A directive such as eslint-disable-next-line, or a triple-slash reference, is read by a tool rather than a person.
# Three stars open a banner rather than a doc comment.
QUERY = """
((comment) @comment
  (#match? @comment "^//")
  (#not-match? @comment "^(///|//[ \t]*(eslint|@ts-|prettier-ignore|biome-ignore|istanbul |c8 |#region|#endregion))"))
((comment) @doc (#match? @doc "^/[*][*]([^*/]|$)"))
"""

_CLASS_LIKE = frozenset(
    {'class_declaration', 'abstract_class_declaration', 'interface_declaration', 'enum_declaration'}
)
_PRIVATE_MODIFIERS = frozenset({b'private', b'protected'})
# A declaration inside one of these is local to a body, so nothing outside it can see the name.
_LOCAL_SCOPES = frozenset({'statement_block', 'class_static_block'})


class TypeScriptProfile(LanguageProfile):
    """TypeScript, whose doc comment is a JSDoc block standing above the declaration it documents."""

    doc_delimiter = '/**'
    doc_frame = DocFrame(opening='/**', prefix=' * ', closing=' */')
    doc_leads_declaration = True
    default_line_width = 80
    signature_tags = ('@param', '@returns', '@type')
    _ROLES = {
        'program': NodeRole.ROOT,
        'comment': NodeRole.COMMENT,
        'export_statement': NodeRole.DEFINITION,
        'ambient_declaration': NodeRole.DEFINITION,
        'function_declaration': NodeRole.DEFINITION,
        'generator_function_declaration': NodeRole.DEFINITION,
        'function_signature': NodeRole.DEFINITION,
        'class_declaration': NodeRole.DEFINITION,
        'abstract_class_declaration': NodeRole.DEFINITION,
        'interface_declaration': NodeRole.DEFINITION,
        'type_alias_declaration': NodeRole.DEFINITION,
        'enum_declaration': NodeRole.DEFINITION,
        'internal_module': NodeRole.DEFINITION,
        'lexical_declaration': NodeRole.DEFINITION,
        'variable_declaration': NodeRole.DEFINITION,
        'variable_declarator': NodeRole.DEFINITION,
        'method_definition': NodeRole.DEFINITION,
        'method_signature': NodeRole.DEFINITION,
        'abstract_method_signature': NodeRole.DEFINITION,
        'public_field_definition': NodeRole.DEFINITION,
        'property_signature': NodeRole.DEFINITION,
        'import_statement': NodeRole.IMPORT,
    }

    def __init__(self, language_id: str, extensions: frozenset[str], language: Language) -> None:
        self.language_id = language_id
        self.extensions = extensions
        self._language = language

    def language(self) -> Language:
        return self._language

    def query(self) -> str:
        return QUERY

    def role_of(self, node_type: str) -> NodeRole:
        return self._ROLES.get(node_type, NodeRole.OTHER)

    def symbol_kind(self, node_type: str) -> SymbolKind:
        if node_type in _CLASS_LIKE:
            return SymbolKind.CLASS
        return SymbolKind.MODULE if node_type == 'internal_module' else SymbolKind.FUNCTION

    def visibility_of(self, name: str) -> Visibility:
        return Visibility.INTERNAL if name.startswith('#') else Visibility.PUBLIC

    def visibility_of_declaration(self, declaration: Node, name: str) -> Visibility:
        """A top-level name is public only when exported, and a member follows its class unless marked private."""
        if self.visibility_of(name) is Visibility.INTERNAL:
            return Visibility.INTERNAL
        if any(
            child.type == 'accessibility_modifier' and child.text in _PRIVATE_MODIFIERS
            for child in declaration.children
        ):
            return Visibility.INTERNAL
        ancestor = declaration.parent
        while ancestor is not None:
            if ancestor.type == 'export_statement':
                return Visibility.PUBLIC
            if ancestor.type in _LOCAL_SCOPES or ancestor.type == 'program':
                return Visibility.INTERNAL
            ancestor = ancestor.parent
        return Visibility.INTERNAL

    def split_delimiter(self, line: str, form: CommentForm) -> DelimiterSplit:
        indent = line[: len(line) - len(line.lstrip())]
        rest = line[len(indent) :].rstrip()
        pattern = _LINE_DELIMITER
        if form is CommentForm.DOC:
            pattern = _DOC_OPENING if rest.startswith('/**') else _DOC_PREFIX
            if rest == _DOC_CLOSING:
                return DelimiterSplit(indent=indent, delimiter=rest, text='')
        opening = pattern.match(rest)
        delimiter = opening.group(1) if opening else ''
        text = rest[len(delimiter) :]
        suffix = ''
        if form is CommentForm.DOC and text.endswith(_DOC_CLOSING):
            text = text[: -len(_DOC_CLOSING)]
            suffix = text[len(text.rstrip()) :] + _DOC_CLOSING
            text = text.rstrip()
        return DelimiterSplit(indent=indent, delimiter=delimiter, text=text, suffix=suffix)


TYPESCRIPT = TypeScriptProfile(
    'typescript', frozenset({'.ts', '.mts', '.cts'}), Language(tree_sitter_typescript.language_typescript())
)
TSX = TypeScriptProfile('tsx', frozenset({'.tsx'}), Language(tree_sitter_typescript.language_tsx()))
