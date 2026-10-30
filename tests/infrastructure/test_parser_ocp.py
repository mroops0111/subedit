import re

import tree_sitter_typescript
import tree_sitter_yaml
from factories import document
from tree_sitter import Language

from subedit.domain import LINE_LAYOUT, CommentForm, CommentPlacement, Document, SymbolKind, Visibility
from subedit.domain.ports import DelimiterSplit
from subedit.infrastructure import TreeSitterParser
from subedit.infrastructure.parsers.languages import CommentOnlyProfile, LanguageProfile, NodeRole


_TS_DELIMITER = re.compile(r'^(/\*\*|/\*|//+)\s?')

TYPESCRIPT_LANGUAGE = Language(tree_sitter_typescript.language_typescript())
TYPESCRIPT_QUERY = '(comment) @comment'


class TypeScriptProfile(LanguageProfile):
    language_id = 'typescript'
    extensions = frozenset({'.ts', '.tsx'})
    doc_delimiter = '/**'
    signature_tags = ('@param', '@returns', '@type')
    canonical_extension = '.ts'
    doc_layout = LINE_LAYOUT
    declares_symbols = True
    _ROLES = {
        'program': NodeRole.ROOT,
        'comment': NodeRole.COMMENT,
        'function_declaration': NodeRole.DEFINITION,
        'class_declaration': NodeRole.DEFINITION,
        'method_definition': NodeRole.DEFINITION,
        'export_statement': NodeRole.DEFINITION,
    }

    def language(self) -> Language:
        return TYPESCRIPT_LANGUAGE

    def query(self) -> str:
        return TYPESCRIPT_QUERY

    def role_of(self, node_type: str) -> NodeRole:
        return self._ROLES.get(node_type, NodeRole.OTHER)

    def symbol_kind(self, node_type: str) -> SymbolKind:
        return SymbolKind.CLASS if node_type == 'class_declaration' else SymbolKind.FUNCTION

    def visibility_of(self, name: str) -> Visibility:
        return Visibility.INTERNAL if name.startswith('_') else Visibility.PUBLIC

    def split_delimiter(self, line: str, form: CommentForm) -> DelimiterSplit:
        indent = line[: len(line) - len(line.lstrip())]
        rest = line[len(indent) :]
        match = _TS_DELIMITER.match(rest)
        if match is None:
            return DelimiterSplit(indent=indent, delimiter='', text=rest.rstrip())
        text = rest[match.end() :].rstrip()
        suffix = ''
        if text.endswith('*/'):
            text, suffix = text[:-2].rstrip(), '*/'
        return DelimiterSplit(indent=indent, delimiter=match.group(1) + ' ', text=text, suffix=suffix)


def test_a_second_grammar_needs_no_parser_change() -> None:
    profile: LanguageProfile = TypeScriptProfile()
    parser = TreeSitterParser((profile,))
    source = '// a leading note\nexport function build(x: string) {\n  // an inner note\n  return x\n}\n'
    blocks = parser.parse(document(source, 'typescript'))

    assert [block.prose().flattened for block in blocks] == ['a leading note', 'an inner note']
    assert blocks[0].placement is CommentPlacement.LEADING_DECLARATION
    assert blocks[1].placement is CommentPlacement.INLINE_BODY


def test_a_typescript_file_header_is_recognised_through_the_profile_root_node() -> None:
    parser = TreeSitterParser((TypeScriptProfile(),))
    source = '// a header note\n\nconst x = 1\n'
    blocks = parser.parse(document(source, 'typescript'))
    assert blocks[0].placement is CommentPlacement.FILE_HEADER


def test_a_typescript_doc_comment_attaches_to_its_class() -> None:
    parser = TreeSitterParser((TypeScriptProfile(),))
    source = '// documents the widget\nclass Widget {}\n'
    blocks = parser.parse(document(source, 'typescript'))

    assert blocks[0].attachment is not None
    assert blocks[0].attachment.name == 'Widget'
    assert blocks[0].attachment.kind is SymbolKind.CLASS


def test_grammar_node_names_come_from_the_profile_not_the_parser() -> None:
    source = 'class Widget {\n  // note\n}\n'
    subject = document(source, 'typescript')

    aware = TreeSitterParser((TypeScriptProfile(),)).parse(subject)
    assert aware[0].placement is CommentPlacement.INLINE_BODY

    class BlindProfile(TypeScriptProfile):
        def role_of(self, node_type: str) -> NodeRole:
            return NodeRole.COMMENT if node_type == 'comment' else NodeRole.OTHER

    blind = TreeSitterParser((BlindProfile(),)).parse(subject)
    assert blind[0].placement is CommentPlacement.INLINE_BODY
    assert blind[0].attachment is None


def test_consecutive_lines_group_under_a_different_grammar() -> None:
    parser = TreeSitterParser((TypeScriptProfile(),))
    source = '// first line,\n// second line.\nconst x = 1\n'
    blocks = parser.parse(document(source, 'typescript'))

    assert len(blocks) == 1
    assert blocks[0].line_count == 2
    assert blocks[0].prose().flattened == 'first line, second line.'


def test_a_format_with_only_line_comments_is_one_more_instance() -> None:
    profile = CommentOnlyProfile(
        'conf',
        frozenset({'.conf'}),
        '.conf',
        Language(tree_sitter_yaml.language()),
        '(comment) @comment',
        root_type='stream',
        line_delimiter=re.compile(r'^(#+\s?)'),
        code_line=lambda line: False,
    )
    parser = TreeSitterParser((profile,))
    blocks = parser.parse(
        Document(uri='file:///a.conf', text='# first line,\n# second line.\nkey: 1\n', language_id='conf')
    )

    assert [block.prose().flattened for block in blocks] == ['first line, second line.']
    assert parser.file_type_named('conf') == profile.file_type
