import re

import tree_sitter_python
from tree_sitter import Language

from ....domain.models.comment import CommentForm, SymbolKind, Visibility
from ....domain.models.comment_layout import QUOTED_DOC_LAYOUT
from ....domain.ports.language_conventions import DelimiterSplit
from .language_profile import LanguageProfile, NodeRole


_DOC_DELIMITER = re.compile(r'^([rRbBuUfF]{0,2})("""|\'\'\')')
_HASH_DELIMITER = re.compile(r'^(#+\s?)')

_LANGUAGE = Language(tree_sitter_python.language())

QUERY = """
(comment) @comment
(module . (expression_statement . (string) @doc .))
(function_definition body: (block . (expression_statement . (string) @doc .)))
(class_definition body: (block . (expression_statement . (string) @doc .)))
"""


class PythonProfile(LanguageProfile):
    language_id = 'python'
    extensions = frozenset({'.py', '.pyi'})
    doc_delimiter = '"""'
    signature_tags = ('Args:', 'Returns:', 'Raises:', 'Yields:', ':param', ':return', ':returns', ':rtype')
    canonical_extension = '.py'
    doc_layout = QUOTED_DOC_LAYOUT
    vendor_directories = frozenset({'venv', 'site-packages', '__pypackages__'})
    _ROLES = {
        'module': NodeRole.ROOT,
        'comment': NodeRole.COMMENT,
        'function_definition': NodeRole.DEFINITION,
        'class_definition': NodeRole.DEFINITION,
        'decorated_definition': NodeRole.DEFINITION,
        'import_statement': NodeRole.IMPORT,
        'import_from_statement': NodeRole.IMPORT,
        'future_import_statement': NodeRole.IMPORT,
    }

    def language(self) -> Language:
        return _LANGUAGE

    def query(self) -> str:
        return QUERY

    def role_of(self, node_type: str) -> NodeRole:
        return self._ROLES.get(node_type, NodeRole.OTHER)

    def symbol_kind(self, node_type: str) -> SymbolKind:
        return SymbolKind.CLASS if node_type == 'class_definition' else SymbolKind.FUNCTION

    def visibility_of(self, name: str) -> Visibility:
        return Visibility.INTERNAL if name.startswith('_') else Visibility.PUBLIC

    def split_delimiter(self, line: str, form: CommentForm) -> DelimiterSplit:
        indent = line[: len(line) - len(line.lstrip())]
        rest = line[len(indent) :]
        if form is CommentForm.DOC:
            delimiter, text, suffix = self._split_doc(rest)
            return DelimiterSplit(indent=indent, delimiter=delimiter, text=text, suffix=suffix)
        hash_delimiter = _HASH_DELIMITER.match(rest)
        if hash_delimiter is None:
            return DelimiterSplit(indent=indent, delimiter='', text=rest.rstrip())
        return DelimiterSplit(
            indent=indent, delimiter=hash_delimiter.group(1), text=rest[hash_delimiter.end() :].rstrip()
        )

    def _split_doc(self, rest: str) -> tuple[str, str, str]:
        opening = _DOC_DELIMITER.match(rest)
        delimiter = opening.group(0) if opening else ''
        body = rest[len(delimiter) :]
        delimiter = opening.group(2) if opening else ''
        suffix = ''
        for candidate in (delimiter, '"""', "'''"):
            if candidate and body.endswith(candidate):
                suffix = candidate
                body = body[: -len(candidate)]
                break
        return delimiter, body.rstrip(), suffix


PYTHON = PythonProfile()
