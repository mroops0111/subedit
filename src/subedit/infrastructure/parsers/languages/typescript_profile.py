import re

import tree_sitter_typescript
from tree_sitter import Language, Node

from ....domain.models.comment import CommentForm, SymbolKind, Visibility
from ....domain.models.comment_layout import FramedDocLayout
from ....domain.models.prose import ProseMarkup
from ....domain.ports.language_conventions import DelimiterSplit
from ...config_sources.formatter_width import WidthSetting
from .code_line import GrammarCodeLine
from .language_profile import LanguageProfile, NodeRole


_LINE_DELIMITER = re.compile(r'^(//+\s?)')
_DOC_OPENING = re.compile(r'^(/\*\*\s?)')
_DOC_PREFIX = re.compile(r'^(\*(?!/)\s?)')
_DOC_CLOSING = '*/'

# A plain /* */ block is usually a license header or a lint directive, so only // and /** */ are prose.
# A directive such as eslint-disable-next-line, or a triple-slash reference, is read by a tool rather than a person.
# Three stars open a banner rather than a doc comment.
_DIRECTIVE = (
    '^(///|//[ \t]*(eslint|@ts-|prettier-ignore|biome-ignore|istanbul |c8 |#region|#endregion)'
    '|/[*][ \t]*(eslint|prettier-ignore|biome-ignore|istanbul |c8 ))'
)

QUERY = f"""
((comment) @comment (#match? @comment "^//") (#not-match? @comment "{_DIRECTIVE}"))
((comment) @directive (#match? @directive "{_DIRECTIVE}"))
((comment) @doc (#match? @doc "^/[*][*]([^*/]|$)"))
"""

_CLASS_LIKE = frozenset(
    {'class_declaration', 'abstract_class_declaration', 'interface_declaration', 'enum_declaration'}
)

_PRIVATE_MODIFIERS = frozenset({b'private', b'protected'})
# A declaration inside one of these is local to a body, so nothing outside it can see the name.
_LOCAL_SCOPES = frozenset({'statement_block', 'class_static_block'})
# A line that opens or closes a bracket, or ends a statement, is code though it cannot parse alone.
# A brace closing on a word is an inline tag such as {@link Store}, which prose holds.
_BLOCK_LINE = re.compile(r'(^\s*[)\]}]|[(\[{;]\s*$|[\s{]}\s*$)')

_STATEMENT_TYPES = frozenset(
    {
        'call_expression',
        'new_expression',
        'await_expression',
        'assignment_expression',
        'augmented_assignment_expression',
        'lexical_declaration',
        'variable_declaration',
        'return_statement',
        'throw_statement',
        'import_statement',
        'export_statement',
        'function_declaration',
        'class_declaration',
    }
)

# A block tag such as @example or @throws opens the tag section, which runs to the end and holds no prose to lay out.
_BLOCK_TAG = re.compile(r'^\s*@[A-Za-z]')


class TypeScriptProfile(LanguageProfile):
    """TypeScript or JavaScript, whose doc comment is a JSDoc block standing above the declaration it documents."""

    doc_delimiter = '/**'
    doc_layout = FramedDocLayout(opening='/**', prefix=' * ', closing_line=' */')
    doc_leads_declaration = True
    directive = re.compile(_DIRECTIVE)
    width_settings = (
        *(
            WidthSetting(name, ('printWidth',))
            for name in ('.prettierrc', '.prettierrc.json', '.prettierrc.yaml', '.prettierrc.yml', '.prettierrc.toml')
        ),
        WidthSetting('package.json', ('prettier', 'printWidth')),
        *(
            WidthSetting(name, key_path)
            for name in ('biome.json', 'biome.jsonc')
            for key_path in (('javascript', 'formatter', 'lineWidth'), ('formatter', 'lineWidth'))
        ),
    )
    vendor_directories = frozenset({'node_modules', 'bower_components', 'jspm_packages'})
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

    def __init__(
        self,
        language_id: str,
        extensions: frozenset[str],
        canonical_extension: str,
        language: Language,
        signature_tags: tuple[str, ...] = ('@param', '@returns', '@return', '@type'),
    ) -> None:
        self.language_id = language_id
        self.signature_tags = signature_tags
        self.extensions = extensions
        self.canonical_extension = canonical_extension
        self._language = language
        code_line = GrammarCodeLine(language, _STATEMENT_TYPES, block_line=_BLOCK_LINE)
        self.doc_markup = ProseMarkup(tag_section=_BLOCK_TAG, example_tag='@example', code_line=code_line)
        self.line_markup = ProseMarkup(code_line=code_line)

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

    def imports_for_effect(self, node: Node) -> bool:
        return node.type == 'import_statement' and not any(
            child.type in ('import_clause', 'import_require_clause') for child in node.named_children
        )

    def exported_names(self, root: Node) -> frozenset[str]:
        """The names exported apart from their declaration, as in "export { build }" or "export default build"."""
        names: set[str] = set()
        for statement in root.named_children:
            if statement.type != 'export_statement':
                continue
            default_value = statement.child_by_field_name('value')
            if default_value is not None and default_value.type == 'identifier':
                names.add(_text(default_value))
            for clause in statement.named_children:
                if clause.type != 'export_clause':
                    continue
                for specifier in clause.named_children:
                    local_name = specifier.child_by_field_name('name')
                    if local_name is not None:
                        names.add(_text(local_name))
        return frozenset(names)

    def visibility_of_declaration(self, declaration: Node, name: str, exported: frozenset[str]) -> Visibility:
        """A top-level name is public only when exported, and a member follows its class unless marked private."""
        if self.visibility_of(name) is Visibility.INTERNAL:
            return Visibility.INTERNAL
        if any(
            child.type == 'accessibility_modifier' and child.text in _PRIVATE_MODIFIERS
            for child in declaration.children
        ):
            return Visibility.INTERNAL
        statement = declaration
        while statement.parent is not None:
            # An ambient declaration describes something that exists globally, so anyone can reach it.
            if statement.parent.type in ('export_statement', 'ambient_declaration'):
                return Visibility.PUBLIC
            if statement.parent.type in _LOCAL_SCOPES:
                return Visibility.INTERNAL
            if statement.parent.type == 'program':
                return Visibility.PUBLIC if _declared_names(statement) & exported else Visibility.INTERNAL
            statement = statement.parent
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
    'typescript', frozenset({'.ts', '.mts', '.cts'}), '.ts', Language(tree_sitter_typescript.language_typescript())
)

TSX = TypeScriptProfile('tsx', frozenset({'.tsx'}), '.tsx', Language(tree_sitter_typescript.language_tsx()))

# JavaScript is TypeScript without the types, and the TSX grammar reads JSX as well.
# Its JSDoc tags carry the only types it has, so no tag restates a signature.
JAVASCRIPT = TypeScriptProfile(
    'javascript',
    frozenset({'.js', '.mjs', '.cjs', '.jsx'}),
    '.js',
    Language(tree_sitter_typescript.language_tsx()),
    signature_tags=(),
)


def _text(node: Node) -> str:
    return (node.text or b'').decode('utf-8')


# A member is exported with the class around it, so what counts is the name the top-level statement declares.
def _declared_names(statement: Node) -> frozenset[str]:
    name = statement.child_by_field_name('name')
    if name is not None:
        return frozenset({_text(name)})
    return frozenset(
        _text(declarator_name)
        for declarator in statement.named_children
        if declarator.type == 'variable_declarator'
        and (declarator_name := declarator.child_by_field_name('name')) is not None
    )
