import re

import tree_sitter_python
from tree_sitter import Language

from ....domain.models.comment import CommentForm, SymbolKind, Visibility
from ....domain.models.comment_layout import QUOTED_DOC_LAYOUT
from ....domain.models.prose import ProseMarkup
from ....domain.ports.language_conventions import DelimiterSplit
from ...config_sources.formatter_width import WidthSetting
from .code_line import GrammarCodeLine
from .language_profile import LanguageProfile, NodeRole


_DOC_DELIMITER = re.compile(r'^([rRbBuUfF]{0,2})("""|\'\'\')')
_HASH_DELIMITER = re.compile(r'^(#+\s?)')

_LANGUAGE = Language(tree_sitter_python.language())

# A clause that continues a block, a bracket opening or closing a call, or a doctest prompt is code,
# though it cannot parse alone.
_BLOCK_LINE = re.compile(
    r'^\s*(?:(?:else|try|finally)\s*:|(?:elif|except)\b.*:|[)\]}]+[,:]?|(?:>>>|\.\.\.)(?:\s.*)?|.*[(\[{])\s*$'
)
_STATEMENT_TYPES = frozenset(
    {
        'call',
        'await',
        'assignment',
        'augmented_assignment',
        'return_statement',
        'raise_statement',
        'assert_statement',
        'delete_statement',
        'import_statement',
        'import_from_statement',
        'global_statement',
        'nonlocal_statement',
        'if_statement',
        'for_statement',
        'while_statement',
        'with_statement',
        'function_definition',
        'class_definition',
    }
)
# "Note: this" parses as an annotation with no value, which a label in prose reads as too.
_CODE_LINE = GrammarCodeLine(
    _LANGUAGE, _STATEMENT_TYPES, block_line=_BLOCK_LINE, required_fields={'assignment': 'right'}
)
# A Google section such as Args:, a NumPy one such as Parameters,
# or a reStructuredText field such as :param opens the sections that close a docstring,
# which hold entries rather than prose to lay out.
_SECTION = re.compile(
    r'^\s*(?:(?:Args|Arguments|Parameters|Params|Keyword Args|Keyword Arguments|Other Parameters|Returns?|Yields?'
    r'|Raises|Exceptions?|Attributes|Examples?|Notes?|Warnings?|Warns|Todo|See Also|References|Methods):?\s*$'
    r'|:(?:param|parameter|arg|argument|key|keyword|type|returns?|rtype|raises?|except|exception|var|ivar|cvar'
    r'|vartype|yields?|ytype)\b|-{3,}\s*$)'
)

# A pragma such as noqa is read by a tool, so the reason after it is no prose to lay out.
_DIRECTIVE = '^#[ \t]*(noqa|type:[ \t]*ignore|pragma|pylint:|fmt:|isort:|ruff:|mypy:|pyright:)'
QUERY = f"""
((comment) @comment (#not-match? @comment "{_DIRECTIVE}"))
((comment) @directive (#match? @directive "{_DIRECTIVE}"))
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
    directive = re.compile(_DIRECTIVE)
    doc_markup = ProseMarkup(tag_section=_SECTION, example_tag='Example', code_line=_CODE_LINE)
    line_markup = ProseMarkup(code_line=_CODE_LINE)
    vendor_directories = frozenset({'venv', 'site-packages', '__pypackages__'})
    width_settings = (
        WidthSetting('ruff.toml', ('line-length',)),
        WidthSetting('.ruff.toml', ('line-length',)),
        WidthSetting('pyproject.toml', ('tool', 'ruff', 'line-length')),
        WidthSetting('pyproject.toml', ('tool', 'black', 'line-length')),
    )
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
