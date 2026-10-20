import re
import typing

from tree_sitter import Language, Node, Parser


# A list item opens with a marker that a grammar reads as an operator, as "- `url` (ssh)" parses as a call.
_LIST_ITEM = re.compile(r'^(?:[-*+]|\d+[.)])\s')


class GrammarCodeLine:
    """Whether a comment line is code commented out, read by parsing the line with the language's own grammar.

    A line is code when it parses cleanly and holds a statement no sentence makes, such as a call or an assignment.
    A line that only opens or closes a block cannot parse alone, so a pattern for such lines backs the grammar up.
    """

    def __init__(
        self,
        language: Language,
        statement_types: frozenset[str],
        *,
        block_line: re.Pattern[str] | None = None,
        required_fields: typing.Mapping[str, str] | None = None,
    ) -> None:
        self._parser = Parser(language)
        self._statement_types = statement_types
        self._block_line = block_line
        # A node that only counts with a field present, such as a Python annotation, which "Note: this" parses as.
        self._required_fields = dict(required_fields or {})
        self._verdicts: dict[str, bool] = {}

    def __call__(self, line: str) -> bool:
        if self._block_line is not None and self._block_line.search(line):
            return True
        text = line.strip()
        if text not in self._verdicts:
            self._verdicts[text] = self._parses_as_statement(text)
        return self._verdicts[text]

    def _parses_as_statement(self, text: str) -> bool:
        if not text or _LIST_ITEM.match(text):
            return False
        root = self._parser.parse(text.encode('utf-8')).root_node
        return not root.has_error and self._holds_statement(root)

    def _holds_statement(self, node: Node) -> bool:
        if node.type in self._statement_types:
            field = self._required_fields.get(node.type)
            if field is None or node.child_by_field_name(field) is not None:
                return True
        return any(self._holds_statement(child) for child in node.named_children)
