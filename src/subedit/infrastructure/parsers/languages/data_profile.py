import re
import typing

import tree_sitter_json
import tree_sitter_yaml
from tree_sitter import Language

from ....domain.models.comment import CommentForm, SymbolKind, Visibility
from ....domain.models.comment_layout import LINE_LAYOUT
from ....domain.models.prose import ProseMarkup
from ....domain.ports.language_conventions import DelimiterSplit
from .language_profile import LanguageProfile, NodeRole


# A comment a tool reads, such as a schema pointer for the YAML language server or a yamllint switch.
_YAML_DIRECTIVE = '^#[ \t]*(yaml-language-server:|yamllint |prettier-ignore|[$]schema)'
_YAML_QUERY = f"""
((comment) @comment (#not-match? @comment "{_YAML_DIRECTIVE}"))
((comment) @directive (#match? @directive "{_YAML_DIRECTIVE}"))
"""
# A plain /* */ block is usually a disabled stretch of settings, so only // is prose, as in TypeScript.
_JSON_QUERY = '((comment) @comment (#match? @comment "^//"))'

_HASH_DELIMITER = re.compile(r'^(#+\s?)')
_SLASH_DELIMITER = re.compile(r'^(//+\s?)')

# A key with no space in it, alone or opening a list item, as in "timeout: 30" or "- uses: actions/checkout".
_YAML_PAIR = re.compile(r'^\s*(?:-\s+)?(?:[^\s:#"\']+|"[^"]*"|\'[^\']*\'):(?:\s+(?P<value>.*))?$')
# A quoted key, a quoted item, or a line holding only brackets, as in "\"timeout\": 30," or "],".
_JSON_LINE = re.compile(r'^\s*(?:"[^"]*"\s*:|"[^"]*",?\s*$|[{}\[\],\s]+$)')


class DataProfile(LanguageProfile):
    """A data format such as YAML or JSON, whose comments note the settings around them and have no doc form."""

    doc_delimiter = ''
    doc_layout = LINE_LAYOUT
    signature_tags = ()
    # The root is left unnamed, since a format with no doc form has nowhere better for a note on the whole file,
    # so no comment counts as a file header.
    _ROLES: typing.ClassVar[dict[str, NodeRole]] = {'comment': NodeRole.COMMENT}

    def __init__(
        self,
        language_id: str,
        extensions: frozenset[str],
        canonical_extension: str,
        language: Language,
        query: str,
        *,
        delimiter: re.Pattern[str],
        code_line: typing.Callable[[str], bool],
        directive: re.Pattern[str] | None = None,
    ) -> None:
        self.language_id = language_id
        self.extensions = extensions
        self.canonical_extension = canonical_extension
        self.directive = directive
        self.line_markup = ProseMarkup(code_line=code_line)
        self._language = language
        self._query = query
        self._delimiter = delimiter

    def language(self) -> Language:
        return self._language

    def query(self) -> str:
        return self._query

    def role_of(self, node_type: str) -> NodeRole:
        return self._ROLES.get(node_type, NodeRole.OTHER)

    def symbol_kind(self, node_type: str) -> SymbolKind:
        return SymbolKind.MODULE

    def visibility_of(self, name: str) -> Visibility:
        return Visibility.INTERNAL

    def split_delimiter(self, line: str, form: CommentForm) -> DelimiterSplit:
        indent = line[: len(line) - len(line.lstrip())]
        rest = line[len(indent) :].rstrip()
        opening = self._delimiter.match(rest)
        delimiter = opening.group(1) if opening else ''
        return DelimiterSplit(indent=indent, delimiter=delimiter, text=rest[len(delimiter) :])


# A label in prose, such as "Note: this runs first.", ends its sentence with a period where a value seldom does.
def _is_yaml_code(line: str) -> bool:
    pair = _YAML_PAIR.match(line)
    if pair is None:
        return False
    value = pair.group('value')
    return value is None or not value.rstrip().endswith('.')


def _is_json_code(line: str) -> bool:
    return bool(_JSON_LINE.match(line))


YAML = DataProfile(
    'yaml',
    frozenset({'.yml', '.yaml'}),
    '.yml',
    Language(tree_sitter_yaml.language()),
    _YAML_QUERY,
    delimiter=_HASH_DELIMITER,
    code_line=_is_yaml_code,
    directive=re.compile(_YAML_DIRECTIVE),
)

JSON = DataProfile(
    'json',
    frozenset({'.json', '.jsonc'}),
    '.json',
    Language(tree_sitter_json.language()),
    _JSON_QUERY,
    delimiter=_SLASH_DELIMITER,
    code_line=_is_json_code,
)
