import pytest
from factories import comments, document
from tree_sitter import Language

from subedit.domain import (
    QUOTED_DOC_LAYOUT,
    CommentForm,
    CommentPlacement,
    Document,
    SymbolKind,
    Visibility,
)
from subedit.domain.ports import DelimiterSplit
from subedit.infrastructure import DEFAULT_PARSER, PYTHON, LanguageProfile, TreeSitterParser
from subedit.infrastructure.parsers.languages import NodeRole


def prose_of(source: str) -> list[str]:
    return [group.prose().flattened for group in comments(source)]


def test_an_unsupported_language_yields_nothing() -> None:
    assert DEFAULT_PARSER.parse(Document(uri='a.rb', text='# hi', language_id='ruby')) == ()
    assert DEFAULT_PARSER.supports('python')
    assert not DEFAULT_PARSER.supports('ruby')


def test_a_hash_comment_is_extracted_without_its_marker() -> None:
    assert prose_of('# a note\n') == ['a note']


def test_a_docstring_is_extracted_even_though_it_is_not_a_comment_node() -> None:
    assert prose_of('def f():\n    """A docstring."""\n') == ['A docstring.']


def test_consecutive_hash_lines_group_into_one_block() -> None:
    blocks = comments('# first line,\n# second line.\nx = 1\n')
    assert len(blocks) == 1
    assert blocks[0].line_count == 2
    assert blocks[0].prose().flattened == 'first line, second line.'


def test_a_blank_line_separates_two_blocks() -> None:
    assert len(comments('# first\n\n# second\nx = 1\n')) == 2


def test_differing_indentation_separates_two_blocks() -> None:
    assert len(comments('def f():\n    # inner\n# outer\n    pass\n')) == 2


def test_a_hash_inside_a_string_literal_is_not_a_comment() -> None:
    assert prose_of('colour = "#ff0000 not a comment"\n') == []


def test_a_string_in_expression_position_that_is_not_first_is_not_a_docstring() -> None:
    assert prose_of('def f():\n    x = 1\n    "not a docstring"\n    return x\n') == []


def test_a_bare_string_statement_after_a_docstring_is_not_a_second_docstring() -> None:
    assert prose_of('def f():\n    """Real."""\n    "decoy"\n') == ['Real.']


def test_a_trailing_comment_excludes_the_code_before_it() -> None:
    blocks = comments('y = x  # trailing note\n')
    assert blocks[0].prose().flattened == 'trailing note'
    assert blocks[0].placement is CommentPlacement.TRAILING


def test_a_trailing_comment_counts_the_code_in_its_physical_width() -> None:
    line = comments('y = x  # trailing note\n')[0].lines[0]
    assert line.indent == 'y = x  '
    assert line.physical_width == len('y = x  # trailing note')


def test_a_trailing_comment_does_not_group_with_a_standalone_one() -> None:
    assert len(comments('y = x  # trailing\n# standalone\nz = 2\n')) == 2


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        ('"""Module level."""\n', CommentPlacement.FILE_HEADER),
        ('# header note\nimport os\n', CommentPlacement.FILE_HEADER),
        ('# leading\ndef f():\n    pass\n', CommentPlacement.LEADING_DECLARATION),
        ('def f():\n    """Doc."""\n', CommentPlacement.LEADING_DECLARATION),
        ('def f():\n    # inside\n    pass\n', CommentPlacement.INLINE_BODY),
        ('x = 1  # trailing\n', CommentPlacement.TRAILING),
    ],
)
def test_placement_classification(source: str, expected: CommentPlacement) -> None:
    assert comments(source)[0].placement is expected


def test_a_comment_after_code_at_module_level_is_not_a_file_header() -> None:
    assert comments('import os\n\n# not a header\nx = 1\n')[0].placement is CommentPlacement.INLINE_BODY


def test_a_comment_separated_from_a_definition_by_a_second_comment_still_attaches() -> None:
    blocks = comments('# one\n# two\ndef build():\n    pass\n')
    assert blocks[0].attachment is not None
    assert blocks[0].attachment.name == 'build'


def test_visibility_follows_the_leading_underscore() -> None:
    public = comments('def build():\n    """Doc."""\n')[0]
    internal = comments('def _helper():\n    """Doc."""\n')[0]

    assert public.attachment is not None
    assert internal.attachment is not None
    assert public.attachment.visibility is Visibility.PUBLIC
    assert internal.attachment.visibility is Visibility.INTERNAL
    assert public.attaches_to_public_symbol
    assert not internal.attaches_to_public_symbol


def test_a_class_docstring_attaches_to_the_class() -> None:
    group = comments('class Widget:\n    """Doc."""\n')[0]
    assert group.attachment is not None
    assert group.attachment.kind is SymbolKind.CLASS
    assert group.attachment.name == 'Widget'


def test_form_distinguishes_docstrings_from_hash_comments() -> None:
    assert comments('def f():\n    """Doc."""\n')[0].form is CommentForm.DOC
    assert comments('# note\n')[0].form is CommentForm.LINE


def test_a_multiline_docstring_keeps_every_physical_line() -> None:
    group = comments('def f():\n    """Summary.\n\n    Detail here.\n    """\n')[0]
    assert group.line_count == 4
    assert group.prose().flattened == 'Summary. Detail here.'


def test_a_prefixed_docstring_delimiter_is_stripped() -> None:
    assert prose_of('def f():\n    r"""Raw doc."""\n') == ['Raw doc.']


def test_single_quoted_docstrings_are_handled() -> None:
    assert prose_of("def f():\n    '''Single quoted.'''\n") == ['Single quoted.']


def test_physical_width_counts_indent_and_marker() -> None:
    source = 'def a():\n    def b():\n        def c():\n            # text\n            pass\n'
    line = comments(source)[0].lines[0]
    assert line.text == 'text'
    assert line.physical_width == len('            # text')


@pytest.mark.parametrize(
    'source',
    [
        '"""Module."""\nimport os\n\n\n# lead\n# more\ndef build(x):\n    """Doc.\n\n    Detail.\n    """\n    # inner\n    return x  # trailing\n',
        'class _Thing:\n    """Doc."""\n\n    def _method(self):\n        # note\n        pass\n',
        '# only a comment\n',
    ],
)
def test_every_block_range_reproduces_its_rendering(source: str) -> None:
    data = source.encode('utf-8')
    for group in comments(source):
        assert data[group.range.start : group.range.end].decode('utf-8') == group.render()


def test_blocks_come_back_in_source_order() -> None:
    source = '"""Header."""\n# middle\ndef f():\n    """Doc."""\n'
    starts = [group.range.start for group in comments(source)]
    assert starts == sorted(starts)


def test_the_profile_satisfies_the_language_profile_port() -> None:
    from subedit.domain import SourceParser
    from subedit.infrastructure import PYTHON, LanguageProfile

    profile: LanguageProfile = PYTHON
    parser: SourceParser = DEFAULT_PARSER
    assert profile.language_id == 'python'
    assert '.py' in profile.extensions
    assert parser.supports('python')


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        ('# note\n@cache\ndef build():\n    pass\n', 'build'),
        ('# note\n@a\n@b\ndef build():\n    pass\n', 'build'),
        ('# note\n@app.command(name="x")\ndef build():\n    pass\n', 'build'),
        ('# note\n@dataclass\nclass Widget:\n    pass\n', 'Widget'),
        ('def outer():\n    """Doc."""\n', 'outer'),
    ],
)
def test_a_decorated_declaration_still_resolves_its_name(source: str, expected: str) -> None:
    group = comments(source)[0]
    assert group.attachment is not None
    assert group.attachment.name == expected


def test_a_decorated_class_is_still_a_class() -> None:
    group = comments('# note\n@dataclass\nclass Widget:\n    pass\n')[0]
    assert group.attachment is not None
    assert group.attachment.kind is SymbolKind.CLASS


def test_a_decorated_private_function_is_still_internal() -> None:
    group = comments('# note\n@cache\ndef _helper():\n    pass\n')[0]
    assert group.attachment is not None
    assert group.attachment.visibility is Visibility.INTERNAL


@pytest.mark.parametrize(
    'source',
    [
        '# note\ndef build():\n    pass\n',
        '# note\n@cache\ndef build():\n    pass\n',
        '# note\nclass Widget:\n    pass\n',
        '# note\n@dataclass\nclass Widget:\n    pass\n',
        '# note\nasync def build():\n    pass\n',
    ],
)
def test_a_leading_declaration_comment_always_names_what_it_documents(source: str) -> None:
    group = comments(source)[0]
    assert group.placement is CommentPlacement.LEADING_DECLARATION
    assert group.attachment is not None, 'leading-declaration without an attachment silently disables rules'


def test_a_trailing_comment_never_documents_the_declaration_below_it() -> None:
    source = 'TOKEN = 1  # a placeholder the tests swap out\n\n\nclass TokenSource:\n    pass\n'
    trailing = comments(source)[0]

    assert trailing.placement is CommentPlacement.TRAILING
    assert trailing.attachment is None, 'a trailing comment describes the code to its left'


@pytest.mark.parametrize(
    'source',
    [
        'x = 1  # tail\ndef build():\n    pass\n',
        'x = 1  # tail\nclass Widget:\n    pass\n',
        'import os  # tail\n\n\n@cache\ndef build():\n    pass\n',
    ],
)
def test_only_a_leading_comment_attaches_to_what_follows(source: str) -> None:
    for group in comments(source):
        if group.placement is not CommentPlacement.LEADING_DECLARATION:
            assert group.attachment is None


def test_a_profile_naming_its_captures_otherwise_yields_nothing() -> None:
    class MisnamedProfile(LanguageProfile):
        language_id = 'python'
        extensions = frozenset({'.py'})
        doc_delimiter = '"""'
        signature_tags = ()
        canonical_extension = '.py'
        doc_layout = QUOTED_DOC_LAYOUT

        def language(self) -> Language:
            return PYTHON.language()

        def query(self) -> str:
            return '(comment) @remark'

        def role_of(self, node_type: str) -> NodeRole:
            return PYTHON.role_of(node_type)

        def symbol_kind(self, node_type: str) -> SymbolKind:
            return PYTHON.symbol_kind(node_type)

        def visibility_of(self, name: str) -> Visibility:
            return PYTHON.visibility_of(name)

        def split_delimiter(self, line: str, form: CommentForm) -> DelimiterSplit:
            return PYTHON.split_delimiter(line, form)

    subject = document('# a note\n')

    assert TreeSitterParser((MisnamedProfile(),)).parse(subject) == (), (
        'a capture named anything but comment or doc is dropped, which is why the names are constants'
    )
    assert TreeSitterParser((PYTHON,)).parse(subject) != ()


def test_a_comment_set_apart_by_a_blank_line_documents_nothing() -> None:
    source = (
        'class C:\n'
        '    def __init__(self):\n'
        '        self.prefix = 1\n\n'
        '    # Provider interface\n\n'
        '    async def get(self):\n'
        '        return 1\n'
    )
    groups = comments(source)
    assert groups[0].attachment is None
    assert groups[0].placement is CommentPlacement.INLINE_BODY


def test_a_comment_touching_the_first_statement_is_no_file_header() -> None:
    source = '# The upstream authorization server.\nISSUER = "https://auth.example.com"\n'
    assert comments(source)[0].placement is not CommentPlacement.FILE_HEADER


def test_a_comment_set_apart_at_the_top_is_a_file_header() -> None:
    source = '# Banner about the module.\n\nISSUER = "https://auth.example.com"\n'
    assert comments(source)[0].placement is CommentPlacement.FILE_HEADER


@pytest.mark.parametrize(
    'source',
    [
        '# The cache warms lazily;\n# the first call pays for it.\nx = 1\n',
        '# Wrap the loader with\n# @cache so it reads the file once.\nx = 1\n',
        'def f():\n    """Return the mapping, which reads as\n    {key: value}\n    """\n',
    ],
)
def test_jsdoc_and_brace_heuristics_stay_out_of_python(source: str) -> None:
    group = comments(source)[0]
    assert all(not segment.is_literal for segment in group.prose().segments()), 'Python marks no tags or code this way'
    assert group.code_ranges() == ()
