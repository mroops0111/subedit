import pytest

from subedit.application import Fixer, Linter, RuleEngine
from subedit.domain import Document, RuleSet
from subedit.infrastructure import ALL_RULES, DEFAULT_PARSER, PYTHON, TYPESCRIPT


ENABLED = frozenset(rule.metadata.rule_id for rule in ALL_RULES)


def fixed(source: str, language_id: str, width: int = 120) -> str:
    suffix = '.py' if language_id == 'python' else '.ts'
    document = Document(uri=f'file:///a{suffix}', text=source, language_id=language_id)
    fixer = Fixer(Linter(DEFAULT_PARSER, RuleEngine(ALL_RULES)))
    return fixer.run(document, RuleSet(enabled_rule_ids=ENABLED, line_width=width)).document.text


@pytest.mark.parametrize(
    ('source', 'language_id'),
    [
        ('def f():\n    """Do it."""\n    # result = compute(a, b)\n    # return result\n    return 1\n', 'python'),
        (
            '/** Do it. */\nexport function f() {\n  // const result = compute(a, b)\n  // return result\n  return 1;\n}\n',
            'typescript',
        ),
        (
            'def f():\n    """Do it."""\n    # if ready:\n    #     start()\n    # else:\n    #     wait()\n    return 1\n',
            'python',
        ),
        (
            '/** Do it. */\nexport function f() {\n  // if (ready) {\n  //   start();\n  // }\n  return 1;\n}\n',
            'typescript',
        ),
        ('def f():\n    """Do it."""\n    # client.send(\n    #     payload,\n    # )\n    return 1\n', 'python'),
        (
            '/** Do it. */\nexport function f() {\n  // client.send(\n  //   payload,\n  // )\n  return 1;\n}\n',
            'typescript',
        ),
    ],
)
def test_commented_out_code_is_never_joined_into_a_sentence(source: str, language_id: str) -> None:
    assert fixed(source, language_id) == source


@pytest.mark.parametrize(
    ('source', 'language_id'),
    [
        (
            'def f():\n    """Do it."""\n    # Wait for the lock\n    # before reading the file.\n    return 1\n',
            'python',
        ),
        (
            '/** Do it. */\nexport function f() {\n  // Wait for the lock\n  // before reading the file.\n  return 1;\n}\n',
            'typescript',
        ),
    ],
)
def test_prose_that_breaks_mid_sentence_is_still_joined(source: str, language_id: str) -> None:
    assert 'Wait for the lock before reading the file.' in fixed(source, language_id)


@pytest.mark.parametrize(
    'section',
    [
        'Args:\n        path: the file to read.',
        ':param path: the file to read.',
        'Parameters\n    ----------\n    path : str\n        The file to read.',
    ],
)
def test_a_docstring_section_is_left_as_written_as_a_jsdoc_tag_section_is(section: str) -> None:
    source = f'def f(path):\n    """Count the lines.\n\n    {section}\n    """\n    return 0\n'
    assert fixed(source, 'python') == source


def test_a_doctest_is_code_rather_than_prose() -> None:
    source = 'def f():\n    """Parse it.\n\n    >>> parse("a; b")\n    [\'a\', \'b\']\n    """\n'
    group = DEFAULT_PARSER.parse(Document(uri='file:///a.py', text=source, language_id='python'))[0]
    assert len(group.code_ranges()) == 1, 'the prompt line is code, and its output is left to the author'


@pytest.mark.parametrize(
    ('line', 'language_id'),
    [
        ('- `git@host:owner/repo` (ssh)', 'typescript'),
        ('* ParamInfo (ArgumentInfo or OptionInfo)', 'python'),
        ('Read the settings file before the client connects.', 'python'),
        ('Read the settings file before the client connects.', 'typescript'),
        ('Note: this', 'python'),
        ('Default: 30', 'typescript'),
    ],
)
def test_prose_that_a_grammar_could_misread_stays_prose(line: str, language_id: str) -> None:
    profile = PYTHON if language_id == 'python' else TYPESCRIPT
    assert not profile.line_markup.is_code(line)


@pytest.mark.parametrize('line', ['result = compute(a, b)', 'return result', 'self.cache.clear()', 'x += 1', ')'])
def test_one_line_of_code_is_code_in_both_languages(line: str) -> None:
    assert PYTHON.line_markup.is_code(line)
    assert TYPESCRIPT.line_markup.is_code(line)
