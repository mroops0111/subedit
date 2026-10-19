import pytest

from subedit.application import Linter, RuleEngine
from subedit.domain import Document, FixKind, RuleSet, RuleSettings
from subedit.infrastructure import ALL_RULES, DEFAULT_PARSER


STRUCTURAL = frozenset({'file-header-comment', 'plain-comment-on-public', 'signature-restating-tag', 'block-too-long'})


def lint(source: str, enabled_rule_ids: frozenset[str] = STRUCTURAL, width: int = 120, **settings: RuleSettings):
    document = Document(uri='file:///a.py', text=source, language_id='python')
    return Linter(DEFAULT_PARSER, RuleEngine(ALL_RULES)).run(
        document, RuleSet(enabled_rule_ids=enabled_rule_ids, line_width=width, settings=settings)
    )


def ids(source: str, **kwargs) -> list[str]:
    return [item.rule_id for item in lint(source, **kwargs).diagnostics]


def test_a_banner_before_the_first_declaration_is_reported() -> None:
    assert 'file-header-comment' in ids('# a banner about this module\nimport os\n')


def test_a_module_docstring_is_also_a_file_header() -> None:
    assert 'file-header-comment' in ids('"""A module banner."""\nimport os\n')


def test_a_comment_attached_to_a_declaration_is_not_a_header() -> None:
    assert 'file-header-comment' not in ids('# documents the builder\ndef build():\n    pass\n')


def test_a_public_symbol_documented_with_a_plain_comment_is_reported() -> None:
    findings = lint('# documents the public builder\ndef build(x):\n    return x\n')
    message = next(item.message for item in findings.diagnostics if item.rule_id == 'plain-comment-on-public')
    assert 'build is public' in message
    assert '"""' in message


def test_an_internal_symbol_may_use_a_plain_comment() -> None:
    assert 'plain-comment-on-public' not in ids('# documents the helper\ndef _helper(x):\n    return x\n')


def test_a_public_symbol_with_a_docstring_is_fine() -> None:
    assert 'plain-comment-on-public' not in ids('def build(x):\n    """Build it."""\n    return x\n')


@pytest.mark.parametrize('tag', ['Args:', 'Returns:', 'Raises:', 'Yields:'])
def test_a_signature_restating_tag_is_reported(tag: str) -> None:
    source = f'def build(x):\n    """Build it.\n\n    {tag}\n        x: the thing\n    """\n'
    assert 'signature-restating-tag' in ids(source)


def test_the_tag_is_quoted_in_the_message() -> None:
    source = 'def build(x):\n    """Build it.\n\n    Args:\n        x: the thing\n    """\n'
    message = next(item.message for item in lint(source).diagnostics if item.rule_id == 'signature-restating-tag')
    assert '"Args:"' in message


def test_one_diagnostic_per_block_even_with_several_tags() -> None:
    source = (
        'def build(x):\n    """Build it.\n\n    Args:\n        x: a thing\n\n    Returns:\n        a thing\n    """\n'
    )
    assert ids(source).count('signature-restating-tag') == 1


def test_prose_that_merely_mentions_a_tag_word_is_fine() -> None:
    assert 'signature-restating-tag' not in ids('def build(x):\n    """Build it, returns quickly."""\n    return x\n')


def test_a_plain_comment_is_not_checked_for_tags() -> None:
    assert 'signature-restating-tag' not in ids('def _f(x):\n    # Args: not a docstring\n    return x\n')


def test_an_overlong_line_comment_is_reported() -> None:
    body = ''.join(f'    # line {index}.\n' for index in range(6))
    assert 'block-too-long' in ids(f'def f():\n{body}    pass\n')


def test_a_short_line_comment_is_fine() -> None:
    assert 'block-too-long' not in ids('def f():\n    # one.\n    # two.\n    pass\n')


def test_the_limit_differs_between_public_and_internal_docstrings() -> None:
    body = '\n'.join(f'    Sentence {index}.' for index in range(12))
    public = f'def build():\n    """Summary.\n\n{body}\n    """\n'
    internal = f'def _helper():\n    """Summary.\n\n{body}\n    """\n'

    assert 'block-too-long' not in ids(public)
    assert 'block-too-long' in ids(internal)


def test_the_limits_are_configurable_per_group() -> None:
    source = 'def f():\n    # one.\n    # two.\n    # three.\n    pass\n'
    assert 'block-too-long' in ids(source, **{'block-too-long': RuleSettings(options={'line': 2})})


def test_every_structural_finding_needs_an_author() -> None:
    report = lint('# a banner\nimport os\n')
    for item in report.diagnostics:
        assert item.fix is not None
        assert item.fix.kind is FixKind.REWRITE
        assert item.needs_author


@pytest.mark.parametrize('rule_id', sorted(STRUCTURAL))
def test_each_rule_can_be_disabled_independently(rule_id: str) -> None:
    source = '# a banner\ndef build(x):\n    """Build it.\n\n    Args:\n        x: a thing\n    """\n'
    assert rule_id not in ids(source, enabled_rule_ids=STRUCTURAL - {rule_id})


@pytest.mark.parametrize(
    'decorator',
    ['', '@cache\n', '@a\n@b\n', '@app.command(name="x")\n'],
)
def test_doc_comment_form_survives_decorators(decorator: str) -> None:
    source = f'# documents the public builder\n{decorator}def build(x):\n    return x\n'
    assert 'plain-comment-on-public' in ids(source)


def test_a_reststructuredtext_returns_field_is_a_signature_tag() -> None:
    source = 'def build(x):\n    """Build it.\n\n    :returns: the thing\n    """\n'
    assert 'signature-restating-tag' in ids(source)
