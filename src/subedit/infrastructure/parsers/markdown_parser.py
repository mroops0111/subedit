import dataclasses

import tree_sitter_markdown
from tree_sitter import Language, Node, Parser

from ...domain.models.document import Document
from ...domain.models.embedded import EmbeddedDocument
from ...domain.models.file_type import FileType
from ...domain.models.markdown import MarkdownBlock, MarkdownBlockKind, MarkdownLine
from ...domain.models.position import SourceRange
from ...domain.ports.source_parser import ParsedDocument, SourceParser


MARKDOWN = FileType('markdown', frozenset({'.md', '.markdown'}), '.md')

_MARKDOWN_LANGUAGE = Language(tree_sitter_markdown.language())
_HEADINGS = frozenset({'atx_heading', 'setext_heading'})

# Code, tables, HTML, and front matter hold no prose, so nothing under them is read.
_LITERAL_BLOCKS = frozenset(
    {
        'fenced_code_block',
        'indented_code_block',
        'html_block',
        'pipe_table',
        'minus_metadata',
        'plus_metadata',
        'link_reference_definition',
    }
)


class MarkdownParser(SourceParser[MarkdownBlock]):
    """Finds the headings and paragraphs of a Markdown document, and skips code, tables, HTML, and quotes."""

    @property
    def file_types(self) -> tuple[FileType, ...]:
        return (MARKDOWN,)

    def read(self, document: Document) -> ParsedDocument[MarkdownBlock]:
        """Turn a Markdown document into the headings and paragraphs the rules read.

        1. Parse the block structure with tree-sitter, keeping byte offsets as every range in this package does.
        2. Walk the tree, skipping code, tables, HTML, and front matter whole, and record where each lies.
        3. Take each heading and paragraph's inline node, which spans its text and nothing around it.
        4. Split that text into lines, each carrying apart the indent or quote marker a container gives it.
        """
        if not self.supports(document.language_id):
            return ParsedDocument()
        source_bytes = document.text.encode('utf-8')
        tree = Parser(_MARKDOWN_LANGUAGE).parse(source_bytes)
        found = _Found()
        self._collect(tree.root_node, source_bytes, _Context(), found)
        return ParsedDocument(tuple(found.blocks), tuple(found.literals), tuple(found.embedded))

    def _collect(self, node: Node, source_bytes: bytes, context: '_Context', found: '_Found') -> None:
        if node.type in _LITERAL_BLOCKS:
            found.literals.append(SourceRange(node.start_byte, node.end_byte))
            if node.type == 'fenced_code_block':
                embedded = self._embedded_code(node, source_bytes)
                if embedded is not None:
                    found.embedded.append(embedded)
            return
        if node.type in _HEADINGS or node.type == 'paragraph':
            block = self._build_block(node, source_bytes, context)
            if block is not None:
                found.blocks.append(block)
            return
        if node.type == 'list':
            context = dataclasses.replace(context, list_depth=context.list_depth + 1)
        elif node.type == 'block_quote':
            context = dataclasses.replace(context, quoted=True)
        for child in node.children:
            self._collect(child, source_bytes, context, found)

    def _embedded_code(self, node: Node, source_bytes: bytes) -> EmbeddedDocument | None:
        """The code of a fenced block whose info string names a language, with what sets each line apart in the host.

        Inside a list item or a block quote, each line opens with an indent or a quote marker.
        That prefix is as wide as the column the fence opens at, so the code keeps none of it.
        Only the block's own children are read, since walking the tokens inside its content crashes the binding.
        """
        info = next((child for child in node.children if child.type == 'info_string'), None)
        content = next((child for child in node.children if child.type == 'code_fence_content'), None)
        if info is None or content is None:
            return None
        words = source_bytes[info.start_byte : info.end_byte].decode('utf-8').split()
        if not words:
            return None
        column = _column(source_bytes, node.start_byte)
        lines: list[str] = []
        host_starts: list[int] = []
        prefixes: list[str] = []
        line_start = content.start_byte - _column(source_bytes, content.start_byte)
        while line_start < content.end_byte:
            line_end = source_bytes.find(b'\n', line_start)
            line_end = len(source_bytes) if line_end == -1 else line_end + 1
            text_start = line_start
            while text_start - line_start < column and source_bytes[text_start : text_start + 1] in (b' ', b'\t', b'>'):
                text_start += 1
            # The content ends just past the closing fence's prefix, which opens no line of code.
            if text_start >= content.end_byte:
                break
            lines.append(source_bytes[text_start:line_end].decode('utf-8'))
            host_starts.append(text_start)
            prefixes.append(source_bytes[line_start:text_start].decode('utf-8'))
            line_start = line_end
        return EmbeddedDocument(
            language_name=words[0], text=''.join(lines), host_starts=tuple(host_starts), prefixes=tuple(prefixes)
        )

    def _build_block(self, node: Node, source_bytes: bytes, context: '_Context') -> MarkdownBlock | None:
        inline = self._inline_of(node)
        if inline is None or inline.start_byte == inline.end_byte:
            return None
        if node.type in _HEADINGS:
            kind, level = MarkdownBlockKind.HEADING, self._heading_level(node)
        else:
            kind, level = MarkdownBlockKind.PARAGRAPH, 0
        parent = node.parent
        return MarkdownBlock(
            range=SourceRange(inline.start_byte, inline.end_byte),
            kind=kind,
            lines=self._split_lines(inline, source_bytes),
            level=level,
            list_depth=context.list_depth,
            opens_item=parent is not None and parent.type == 'list_item' and self._first_block(parent) == node,
            quoted=context.quoted,
            leads_into_list=kind is MarkdownBlockKind.HEADING and self._next_block_type(node) == 'list',
        )

    # A list item's children begin with its marker, so the first block is the first child that holds text.
    def _first_block(self, item: Node) -> Node | None:
        return next((child for child in item.children if not child.type.startswith('list_marker')), None)

    def _next_block_type(self, heading: Node) -> str | None:
        sibling = heading.next_named_sibling
        return sibling.type if sibling is not None else None

    def _inline_of(self, node: Node) -> Node | None:
        for child in node.children:
            if child.type == 'inline':
                return child
            # A setext heading holds its text in a paragraph above the underline.
            if child.type == 'paragraph':
                return self._inline_of(child)
        return None

    def _heading_level(self, node: Node) -> int:
        for child in node.children:
            marker = child.type
            if marker.startswith('atx_h') and marker.endswith('_marker'):
                return int(marker[len('atx_h')])
            if marker == 'setext_h1_underline':
                return 1
            if marker == 'setext_h2_underline':
                return 2
        return 0

    def _split_lines(self, inline: Node, source_bytes: bytes) -> tuple[MarkdownLine, ...]:
        # Inside a list item or a block quote,
        # each later line opens with a continuation node holding its indent or marker.
        prefix_ends: dict[int, int] = {}
        for child in inline.children:
            if child.type == 'block_continuation':
                row = _row(source_bytes, child.start_byte)
                prefix_ends[row] = max(prefix_ends.get(row, 0), child.end_byte)
        lines: list[MarkdownLine] = []
        line_start = inline.start_byte
        row = _row(source_bytes, inline.start_byte)
        while line_start <= inline.end_byte:
            newline = source_bytes.find(b'\n', line_start, inline.end_byte)
            line_end = inline.end_byte if newline == -1 else newline
            text_start = line_start
            if lines:
                text_start = prefix_ends.get(row, line_start)
                while text_start < line_end and source_bytes[text_start : text_start + 1] in (b' ', b'\t'):
                    text_start += 1
            lines.append(
                MarkdownLine(
                    range=SourceRange(text_start, line_end),
                    text=source_bytes[text_start:line_end].decode('utf-8'),
                    prefix=source_bytes[line_start:text_start].decode('utf-8'),
                )
            )
            if newline == -1:
                break
            line_start = newline + 1
            row += 1
        return tuple(lines)


@dataclasses.dataclass(frozen=True, slots=True)
class _Context:
    """Where the walk stands, inside how many lists and whether inside a quote."""

    list_depth: int = 0
    quoted: bool = False


@dataclasses.dataclass(slots=True)
class _Found:
    blocks: list[MarkdownBlock] = dataclasses.field(default_factory=list)
    literals: list[SourceRange] = dataclasses.field(default_factory=list)
    embedded: list[EmbeddedDocument] = dataclasses.field(default_factory=list)


# Rows and columns are counted from the bytes,
# since reading a node's start point from the Markdown grammar corrupts memory in the tree-sitter binding.
def _row(source_bytes: bytes, offset: int) -> int:
    return source_bytes.count(b'\n', 0, offset)


def _column(source_bytes: bytes, offset: int) -> int:
    return offset - (source_bytes.rfind(b'\n', 0, offset) + 1)
