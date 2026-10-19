from tree_sitter import Node, Parser, Query, QueryCursor

from ...domain.models.comment import CommentForm, CommentGroup, CommentLine, CommentPlacement, SymbolRef
from ...domain.models.document import Document
from ...domain.models.position import SourceRange
from ...domain.ports.source_parser import SourceParser
from .languages import LanguageProfile, NodeRole


# Every profile must spell its captures this way, and the type system cannot check it.
# A query that names them otherwise yields nothing, silently.
COMMENT_CAPTURE = 'comment'
DOC_CAPTURE = 'doc'


class TreeSitterParser(SourceParser):
    def __init__(self, profiles: tuple[LanguageProfile, ...]) -> None:
        self._profiles = {profile.language_id: profile for profile in profiles}

    def supports(self, language_id: str) -> bool:
        return language_id in self._profiles

    def parse(self, document: Document) -> tuple[CommentGroup, ...]:
        """Turn source text into the comment groups the rules read.

        1. Look up the profile. An unknown language yields nothing rather than raising.
        2. Encode to bytes, because every offset this package stores is a byte offset.
        3. Parse with tree-sitter and run the profile query over the tree.
        4. Build one group per doc comment, since each already arrives as a single node.
        5. Group adjacent line comments first,
           because three consecutive hashes are three nodes sharing one sentence.
        6. Sort by position, so a caller reading the result walks the file in order.
        """
        profile = self._profiles.get(document.language_id)
        if profile is None:
            return ()
        source_bytes = document.text.encode('utf-8')
        tree = Parser(profile.language()).parse(source_bytes)
        grouped_captures = self._run_query(profile, tree.root_node)
        exported = profile.exported_names(tree.root_node)
        comment_groups = [
            self._build_doc_group(profile, document, node, exported) for node in grouped_captures[DOC_CAPTURE]
        ]
        comment_groups.extend(
            self._build_line_group(profile, document, group, exported)
            for group in self._group_adjacent_comments(profile, document, grouped_captures[COMMENT_CAPTURE])
        )
        return tuple(sorted(comment_groups, key=lambda group: group.range.start))

    def _run_query(self, profile: LanguageProfile, root: Node) -> dict[str, list[Node]]:
        query = Query(profile.language(), profile.query())
        captures_by_name = QueryCursor(query).captures(root)
        # A node can match several patterns at once, so the same byte offset arrives twice.
        grouped_captures: dict[str, list[Node]] = {COMMENT_CAPTURE: [], DOC_CAPTURE: []}
        for name, nodes in captures_by_name.items():
            grouped_captures.setdefault(name, []).extend(nodes)
        for name, nodes in grouped_captures.items():
            seen_offsets: set[int] = set()
            unique_nodes = [
                node for node in nodes if not (node.start_byte in seen_offsets or seen_offsets.add(node.start_byte))
            ]
            grouped_captures[name] = sorted(unique_nodes, key=lambda node: node.start_byte)
        return grouped_captures

    def _group_adjacent_comments(
        self, profile: LanguageProfile, document: Document, nodes: list[Node]
    ) -> list[list[Node]]:
        groups: list[list[Node]] = []
        for node in nodes:
            if groups and self._joins_previous_group(profile, document, groups[-1][-1], node):
                groups[-1].append(node)
            else:
                groups.append([node])
        return groups

    # Same column, next line, and neither one trailing.
    # A trailing comment describes the code to its left, so it never joins what sits below it.
    def _joins_previous_group(self, profile: LanguageProfile, document: Document, previous: Node, node: Node) -> bool:
        if previous.start_point[0] != node.start_point[0] - 1:
            return False
        if self._is_trailing_comment(document, previous) or self._is_trailing_comment(document, node):
            return False
        return previous.start_point[1] == node.start_point[1]

    def _is_trailing_comment(self, document: Document, node: Node) -> bool:
        line = document.positions.line_text(node.start_point[0])
        return bool(line[: node.start_point[1]].strip())

    def _build_line_group(
        self, profile: LanguageProfile, document: Document, nodes: list[Node], exported: frozenset[str]
    ) -> CommentGroup:
        lines = tuple(self._build_comment_line(profile, document, node, CommentForm.LINE) for node in nodes)
        placement = self._classify_placement(profile, document, nodes[-1], is_doc=False)
        return CommentGroup(
            range=SourceRange(lines[0].range.start, lines[-1].range.end),
            lines=lines,
            form=CommentForm.LINE,
            placement=placement,
            attachment=self._resolve_attachment(profile, nodes[-1], exported, is_doc=False, opening=nodes[0])
            if placement is CommentPlacement.LEADING_DECLARATION
            else None,
            markup=profile.line_markup,
        )

    def _build_doc_group(
        self, profile: LanguageProfile, document: Document, node: Node, exported: frozenset[str]
    ) -> CommentGroup:
        lines: list[CommentLine] = []
        for line_number in range(node.start_point[0], node.end_point[0] + 1):
            marker_split = profile.split_delimiter(document.positions.line_text(line_number), CommentForm.DOC)
            lines.append(
                CommentLine(
                    range=document.positions.line_range(line_number),
                    indent=marker_split.indent,
                    delimiter=marker_split.delimiter,
                    text=marker_split.text,
                    suffix=marker_split.suffix,
                )
            )
        placement = self._classify_placement(profile, document, node, is_doc=True)
        return CommentGroup(
            range=SourceRange(lines[0].range.start, lines[-1].range.end),
            lines=tuple(lines),
            form=CommentForm.DOC,
            placement=placement,
            attachment=self._resolve_attachment(profile, node, exported, is_doc=True)
            if placement is CommentPlacement.LEADING_DECLARATION
            else None,
            layout=profile.doc_layout,
            markup=profile.doc_markup,
        )

    # Width is measured across indent, delimiter, and text together.
    # Vale measures the extracted content alone, which is why a deeply indented comment passes there.
    def _build_comment_line(
        self, profile: LanguageProfile, document: Document, node: Node, form: CommentForm
    ) -> CommentLine:
        line_number, column = node.start_point
        line_text = document.positions.line_text(line_number)
        marker_split = profile.split_delimiter(line_text[column:], form)
        return CommentLine(
            range=document.positions.line_range(line_number),
            indent=line_text[:column] + marker_split.indent,
            delimiter=marker_split.delimiter,
            text=marker_split.text,
            suffix=marker_split.suffix,
        )

    def _classify_placement(
        self,
        profile: LanguageProfile,
        document: Document,
        node: Node,
        *,
        is_doc: bool,
    ) -> CommentPlacement:
        if is_doc and not profile.doc_leads_declaration:
            owner = self._find_owning_definition(profile, node)
            return CommentPlacement.FILE_HEADER if owner is None else CommentPlacement.LEADING_DECLARATION
        if self._is_trailing_comment(document, node):
            return CommentPlacement.TRAILING
        if self._find_next_definition(profile, node) is not None:
            return CommentPlacement.LEADING_DECLARATION
        parent = node.parent
        is_root = parent is not None and profile.role_of(parent.type) is NodeRole.ROOT
        if is_root and not self._has_code_before(profile, node) and not self._touches_next_code(profile, node):
            return CommentPlacement.FILE_HEADER
        return CommentPlacement.INLINE_BODY

    # A comment on the line right above a statement describes that statement, even at the top of a file.
    # Imports are the exception, since a comment over them is a banner rather than a note on one import,
    # unless the import runs only for its effect, such as patching a library, which only a comment explains.
    def _touches_next_code(self, profile: LanguageProfile, node: Node) -> bool:
        candidate = node.next_named_sibling
        if candidate is None or not self._is_adjacent(node, candidate):
            return False
        role = profile.role_of(candidate.type)
        return role is not NodeRole.COMMENT and (role is not NodeRole.IMPORT or profile.imports_for_effect(candidate))

    # A blank line between a comment and what follows sets the comment apart, as a section divider does.
    def _is_adjacent(self, upper: Node, lower: Node) -> bool:
        return lower.start_point[0] == upper.end_point[0] + 1

    def _has_code_before(self, profile: LanguageProfile, node: Node) -> bool:
        parent = node.parent
        if parent is None:
            return False
        return any(
            sibling.start_byte < node.start_byte and profile.role_of(sibling.type) is not NodeRole.COMMENT
            for sibling in parent.named_children
        )

    def _find_next_definition(self, profile: LanguageProfile, node: Node) -> Node | None:
        previous = node
        candidate = node.next_named_sibling
        while candidate is not None and self._is_adjacent(previous, candidate):
            role = profile.role_of(candidate.type)
            if role is NodeRole.DEFINITION:
                return candidate
            if role is not NodeRole.COMMENT:
                return None
            previous = candidate
            candidate = candidate.next_named_sibling
        return None

    def _find_owning_definition(self, profile: LanguageProfile, node: Node) -> Node | None:
        ancestor = node.parent
        while ancestor is not None:
            role = profile.role_of(ancestor.type)
            if role is NodeRole.DEFINITION:
                return ancestor
            if role is NodeRole.ROOT:
                return None
            ancestor = ancestor.parent
        return None

    # Only a leading declaration documents a symbol, and CommentGroup rejects any other pairing.
    def _resolve_attachment(
        self,
        profile: LanguageProfile,
        node: Node,
        exported: frozenset[str],
        *,
        is_doc: bool,
        opening: Node | None = None,
    ) -> SymbolRef | None:
        lives_inside = is_doc and not profile.doc_leads_declaration
        definition_node = (
            self._find_owning_definition(profile, node) if lives_inside else self._find_next_definition(profile, node)
        )
        if definition_node is None:
            return None
        if not is_doc and opening is not None and self._heads_a_run(profile, opening, definition_node):
            return None
        declaration = self._find_named_declaration(profile, definition_node)
        name = self._declared_name(declaration)
        if declaration is None or name is None:
            return None
        return SymbolRef(
            name=name,
            kind=profile.symbol_kind(declaration.type),
            visibility=profile.visibility_of_declaration(declaration, name, exported),
        )

    # A plain comment opening a paragraph over a run of declarations heads the run, so it documents none alone.
    # One in mid paragraph sits among the declarations, so it documents the one under it.
    # A value and a type of the same name, as zod pairs a schema with its inferred type, are one declaration.
    def _heads_a_run(self, profile: LanguageProfile, opening: Node, definition_node: Node) -> bool:
        above = opening.prev_named_sibling
        if above is not None and self._is_adjacent(above, opening):
            return False
        name = self._declared_name(self._find_named_declaration(profile, definition_node))
        previous, following = definition_node, definition_node.next_named_sibling
        while following is not None and self._is_adjacent(previous, following):
            if profile.role_of(following.type) is not NodeRole.DEFINITION:
                return False
            if self._declared_name(self._find_named_declaration(profile, following)) != name:
                return True
            previous, following = following, following.next_named_sibling
        return False

    def _declared_name(self, declaration: Node | None) -> str | None:
        name_node = declaration.child_by_field_name('name') if declaration is not None else None
        if name_node is None or name_node.text is None:
            return None
        return name_node.text.decode('utf-8')

    # A decorated definition wraps the real one and carries no name field of its own,
    # so the search descends until it reaches whichever node actually names something.
    def _find_named_declaration(self, profile: LanguageProfile, node: Node) -> Node | None:
        if node.child_by_field_name('name') is not None:
            return node
        for child_node in node.named_children:
            if profile.role_of(child_node.type) is NodeRole.DEFINITION:
                named_declaration = self._find_named_declaration(profile, child_node)
                if named_declaration is not None:
                    return named_declaration
        return None
