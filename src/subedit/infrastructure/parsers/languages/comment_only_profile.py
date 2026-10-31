import re
import typing

import tree_sitter_json
import tree_sitter_yaml
from tree_sitter import Language

from ....domain.models.prose import ProseMarkup
from .language_profile import LanguageProfile, NodeRole


# A comment a tool reads, such as a schema pointer for the YAML language server or a yamllint switch.
_YAML_DIRECTIVE = '^#[ \t]*(yaml-language-server:|yamllint |prettier-ignore|[$]schema)'
_YAML_QUERY = f"""
((comment) @comment (#not-match? @comment "{_YAML_DIRECTIVE}"))
((comment) @directive (#match? @directive "{_YAML_DIRECTIVE}"))
"""
# A plain /* */ block is usually a disabled stretch of settings, so only // is prose, as in TypeScript.
_JSON_QUERY = '((comment) @comment (#match? @comment "^//"))'

# A key with no space in it, alone or opening a list item, as in "timeout: 30" or "- uses: actions/checkout".
_YAML_PAIR = re.compile(r'^\s*(?:-\s+)?(?:[^\s:#"\']+|"[^"]*"|\'[^\']*\'):(?:\s+(?P<value>.*))?$')
# A quoted key, a quoted item, or a line holding only brackets, as in "\"timeout\": 30," or "],".
_JSON_LINE = re.compile(r'^\s*(?:"[^"]*"\s*:|"[^"]*",?\s*$|[{}\[\],\s]+$)')


class CommentOnlyProfile(LanguageProfile):
    """A format whose only prose is its line comments, such as YAML or JSON, set up from its grammar and syntax.

    Another such format, such as TOML or a shell script, is one more instance with its own grammar and delimiter.
    """

    def __init__(
        self,
        language_id: str,
        extensions: frozenset[str],
        canonical_extension: str,
        language: Language,
        query: str,
        *,
        root_type: str,
        line_delimiter: re.Pattern[str],
        code_line: typing.Callable[[str], bool],
        directive: re.Pattern[str] | None = None,
        generated_names: frozenset[str] = frozenset(),
    ) -> None:
        self.language_id = language_id
        self.extensions = extensions
        self.canonical_extension = canonical_extension
        self.line_delimiter = line_delimiter
        self.line_markup = ProseMarkup(code_line=code_line)
        self.directive = directive
        self.generated_names = generated_names
        self.node_roles = {root_type: NodeRole.ROOT, 'comment': NodeRole.COMMENT}
        self._language = language
        self._query = query

    def language(self) -> Language:
        return self._language

    def query(self) -> str:
        return self._query


# A label in prose, such as "Note: this runs first.", ends its sentence with a period where a value seldom does.
def _is_yaml_code(line: str) -> bool:
    pair = _YAML_PAIR.match(line)
    if pair is None:
        return False
    value = pair.group('value')
    return value is None or not value.rstrip().endswith('.')


def _is_json_code(line: str) -> bool:
    return bool(_JSON_LINE.match(line))


YAML = CommentOnlyProfile(
    'yaml',
    frozenset({'.yml', '.yaml'}),
    '.yml',
    Language(tree_sitter_yaml.language()),
    _YAML_QUERY,
    root_type='stream',
    line_delimiter=re.compile(r'^(#+\s?)'),
    code_line=_is_yaml_code,
    directive=re.compile(_YAML_DIRECTIVE),
    generated_names=frozenset({'pnpm-lock.yaml'}),
)

JSON = CommentOnlyProfile(
    'json',
    frozenset({'.json', '.jsonc'}),
    '.json',
    Language(tree_sitter_json.language()),
    _JSON_QUERY,
    root_type='document',
    line_delimiter=re.compile(r'^(//+\s?)'),
    code_line=_is_json_code,
    generated_names=frozenset({'package-lock.json', 'npm-shrinkwrap.json'}),
)
