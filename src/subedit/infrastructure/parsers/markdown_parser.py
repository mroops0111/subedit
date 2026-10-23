import tree_sitter_markdown
from tree_sitter import Language, Node, Parser

from ...domain.models.document import Document
from ...domain.models.file_type import FileType
from ...domain.models.markdown import MarkdownBlock, MarkdownBlockKind, MarkdownLine
from ...domain.models.position import SourceRange
from ...domain.ports.source_parser import ParsedDocument, SourceParser


MARKDOWN_LANGUAGE = Language(tree_sitter_markdown.language())
MARKDOWN = FileType('markdown', frozenset({'.md', '.markdown'}), '.md')

HEADINGS = frozenset({'atx_heading', 'setext_heading'})
# Code, tables, HTML, and front matter hold no prose, so nothing under them is read.
LITERAL_BLOCKS = frozenset(
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
        tree = Parser(MARKDOWN_LANGUAGE).parse(source_bytes)
        blocks: list[MarkdownBlock] = []
        literals: list[SourceRange] = []
        self._collect(tree.root_node, source_bytes, 0, blocks, literals)
        return ParsedDocument(tuple(blocks), tuple(literals))

    def _collect(
        self,
        node: Node,
        source_bytes: bytes,
        list_depth: int,
        blocks: list[MarkdownBlock],
        literals: list[SourceRange],
    ) -> None:
        if node.type in LITERAL_BLOCKS:
            literals.append(SourceRange(node.start_byte, node.end_byte))
            return
        if node.type in HEADINGS or node.type == 'paragraph':
            block = self._build_block(node, source_bytes, list_depth)
            if block is not None:
                blocks.append(block)
            return
        depth = list_depth + 1 if node.type == 'list' else list_depth
        for child in node.children:
            self._collect(child, source_bytes, depth, blocks, literals)

    def _build_block(self, node: Node, source_bytes: bytes, list_depth: int) -> MarkdownBlock | None:
        inline = self._inline_of(node)
        if inline is None or inline.start_byte == inline.end_byte:
            return None
        if node.type in HEADINGS:
            kind, level = MarkdownBlockKind.HEADING, self._heading_level(node)
        else:
            kind, level = MarkdownBlockKind.PARAGRAPH, 0
        return MarkdownBlock(
            range=SourceRange(inline.start_byte, inline.end_byte),
            kind=kind,
            lines=self._split_lines(inline, source_bytes),
            level=level,
            list_depth=list_depth,
        )

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
                row = child.start_point.row
                prefix_ends[row] = max(prefix_ends.get(row, 0), child.end_byte)
        lines: list[MarkdownLine] = []
        line_start = inline.start_byte
        row = inline.start_point.row
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
