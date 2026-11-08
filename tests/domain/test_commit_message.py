import pytest
from factories import commit_message, fixed, found, lint, rule_set

from subedit.domain import CommitBody, CommitSubject, RuleSettings, Severity
from subedit.infrastructure import DEFAULT_PARSER


# git's own width for a commit message body.
GIT_WIDTH = 72
CONVENTIONAL = {'subject-style': RuleSettings(options={'style': 'conventional'})}


def units(text: str) -> tuple[object, ...]:
    return DEFAULT_PARSER.parse(commit_message(text))


def ids(text: str, **settings: RuleSettings) -> list[str]:
    return found(lint(commit_message(text), rule_set(width=GIT_WIDTH, settings=settings)))


def fix(text: str, **settings: RuleSettings) -> str:
    return fixed(commit_message(text), rule_set(width=GIT_WIDTH, settings=settings))


def test_a_message_reads_as_its_subject_and_its_body() -> None:
    subject, body = units('feat(cli): read a draft\n\nThe body runs here.\n')
    assert isinstance(subject, CommitSubject)
    assert (subject.prefix, subject.description) == ('feat(cli): ', 'read a draft')
    assert isinstance(body, CommitBody)
    assert body.render() == 'The body runs here.'


@pytest.mark.parametrize(
    'text',
    [
        pytest.param('Fix it\n\nCo-authored-by: A Person <a@example.com>\nCloses #105\n', id='trailers'),
        pytest.param('Fix it\n\n# Please enter the commit message.\n# On branch master\n', id='comments'),
        pytest.param('Fix it\n# ------------------------ >8 ------------------------\ndiff --git a b\n', id='scissors'),
    ],
)
def test_trailers_and_what_git_adds_are_left_unread(text: str) -> None:
    assert [type(unit) for unit in units(text)] == [CommitSubject]


def test_a_message_of_comments_alone_has_nothing_to_read() -> None:
    assert units('\n# Please enter the commit message.\n') == ()


def test_a_body_is_laid_out_by_clause_within_the_width() -> None:
    body = 'The parser reads the subject and the body of a message apart,\nso a rule on one never reads the other.\n'
    assert fix(f'Read a message\n\n{body}') == (
        'Read a message\n\nThe parser reads the subject and the body of a message apart,\n'
        'so a rule on one never reads the other.\n'
    )
    assert fix('Read a message\n\nThe parser reads it\napart.\n') == 'Read a message\n\nThe parser reads it apart.\n'


def test_a_long_trailer_is_never_laid_out() -> None:
    assert (
        ids('Fix it\n\nCo-authored-by: A Person With A Very Long Name Indeed <a.person@a-long-domain.example.com>\n')
        == []
    )


def test_a_subject_past_the_limit_needs_a_rewrite() -> None:
    subject = 'Fix ' + 'the parser ' * 7
    assert ids(subject.strip() + '\n') == ['subject-too-long']
    assert ids('Fix the parser\n', **{'subject-too-long': RuleSettings(options={'max-subject-characters': 10})}) == [
        'subject-too-long'
    ]


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        pytest.param('Fix the parser.\n', 'Fix the parser\n', id='period'),
        pytest.param('fix the parser\n', 'Fix the parser\n', id='capital'),
        pytest.param('mm: fix the parser\n', 'mm: fix the parser\n', id='subsystem keeps its case'),
        pytest.param('iOS: fix the parser\n', 'iOS: fix the parser\n', id='name prefix'),
        pytest.param('iOS builds work again\n', 'iOS builds work again\n', id='name'),
    ],
)
def test_a_git_subject_opens_with_a_capital_and_ends_with_no_period(text: str, expected: str) -> None:
    assert fix(text) == expected


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        pytest.param('feat: Read a draft\n', 'feat: read a draft\n', id='capital'),
        pytest.param('fix(cli)!: drop a flag.\n', 'fix(cli)!: drop a flag\n', id='scope, breaking mark, and period'),
        pytest.param('docs: explain OAuth setup\n', 'docs: explain OAuth setup\n', id='lowercase'),
    ],
)
def test_a_conventional_subject_opens_in_lowercase_after_its_type(text: str, expected: str) -> None:
    assert fix(text, **CONVENTIONAL) == expected


@pytest.mark.parametrize('text', ['Read a draft\n', 'chire: bump the group\n', 'enhance: report a break\n'])
def test_a_conventional_subject_names_a_type_it_lists(text: str) -> None:
    assert ids(text, **CONVENTIONAL) == ['subject-style']


def test_a_project_lists_its_own_types() -> None:
    settings = {'subject-style': RuleSettings(options={'style': 'conventional', 'types': ('enhance',)})}
    assert ids('enhance: report a break\n', **settings) == []
    assert ids('feat: report a break\n', **settings) == ['subject-style']


@pytest.mark.parametrize('word', ['Added', 'Adds', 'Adding', 'Updated'])
def test_a_subject_that_reports_the_change_is_a_warning(word: str) -> None:
    report = lint(commit_message(f'{word} the parser\n'), rule_set(width=GIT_WIDTH))
    [finding] = report.diagnostics
    assert (finding.rule_id, finding.severity) == ('subject-not-imperative', Severity.WARNING)


@pytest.mark.parametrize('word', ['Fix', 'Bring', 'Embed', 'Focus', 'Process', 'Use'])
def test_an_instruction_passes(word: str) -> None:
    assert ids(f'{word} the parser\n') == []


def test_a_body_under_the_subject_gets_a_blank_line() -> None:
    assert ids('Fix the parser\nIt dropped a line.\n') == ['missing-blank-line']
    assert fix('Fix the parser\nIt dropped a line.\n') == 'Fix the parser\n\nIt dropped a line.\n'


def test_wording_rules_read_the_description_but_not_the_prefix() -> None:
    assert ids('feat: read a draft\n', **CONVENTIONAL) == []
    assert ids('Read the draft: then check it\n') == ['mid-sentence-colon']
