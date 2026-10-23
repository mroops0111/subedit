import ast
import io
import pathlib
import tokenize

import pytest

from subedit.domain import CommentForm, Document
from subedit.infrastructure import COMMENT_PARSER, DEFAULT_PARSER


DEFINITIONS = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

CORPORA = [
    pathlib.Path(__file__).resolve().parent.parent / 'src',
    pathlib.Path.home() / 'mroops' / 'side-projects' / 'openapi-mcp-gateway' / 'src',
]


def oracle_comment_lines(source: str) -> set[int]:
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    return {token.start[0] for token in tokens if token.type == tokenize.COMMENT}


def oracle_docstring_lines(source: str) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, DEFINITIONS):
            continue
        if ast.get_docstring(node, clean=False) is None:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr):
            found.add(first.lineno)
    return found


def parsed_lines(source: str) -> tuple[set[int], set[int]]:
    document = Document(uri='file:///corpus.py', text=source, language_id='python')
    mapper = document.positions
    comments: set[int] = set()
    docstrings: set[int] = set()
    for group in COMMENT_PARSER.parse(document):
        rows = {mapper.to_position(line.range.start).line + 1 for line in group.lines}
        if group.form is CommentForm.DOC:
            docstrings.add(min(rows))
        else:
            comments |= rows
    # A directive such as noqa is a comment to the tokenizer, though no rule reads it as prose.
    comments |= {mapper.to_position(directive.start).line + 1 for directive in DEFAULT_PARSER.read(document).skipped}
    return comments, docstrings


def corpus_files() -> list[pathlib.Path]:
    return [path for root in CORPORA if root.is_dir() for path in sorted(root.rglob('*.py'))]


@pytest.mark.parametrize(
    'source',
    [
        'colour = "#ff0000 not a comment"\n',
        'def f():\n    x = 1\n    "not a docstring"\n',
        'def f():\n    """Real."""\n    "decoy"\n',
        'x = 1  # trailing\n',
        '"""Module."""\n# after\ndef g():\n    """Doc."""\n    # inner\n',
        's = """\n# not a comment\n"""\n',
    ],
)
def test_extraction_matches_the_stdlib_oracle(source: str) -> None:
    comments, docstrings = parsed_lines(source)
    assert comments == oracle_comment_lines(source)
    assert docstrings == oracle_docstring_lines(source)


def test_extraction_matches_the_oracle_across_the_corpus() -> None:
    files = corpus_files()
    if not files:
        pytest.skip('no corpus available')

    disagreements: list[str] = []
    for path in files:
        source = path.read_text(encoding='utf-8')
        try:
            expected_comments = oracle_comment_lines(source)
            expected_docstrings = oracle_docstring_lines(source)
        except (SyntaxError, tokenize.TokenError):
            continue
        comments, docstrings = parsed_lines(source)
        if comments != expected_comments:
            disagreements.append(f'{path.name} comments {sorted(comments ^ expected_comments)}')
        if docstrings != expected_docstrings:
            disagreements.append(f'{path.name} docstrings {sorted(docstrings ^ expected_docstrings)}')

    assert not disagreements, f'{len(disagreements)} files disagree with the stdlib oracle: {disagreements[:5]}'
