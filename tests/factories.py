import pathlib
import typing

from subedit.application import Fixer, Linter, RuleEngine
from subedit.domain import (
    Document,
    Report,
    Rule,
    RuleSet,
    RuleSettings,
    SourceRange,
    TextEdit,
    apply_edits,
)
from subedit.domain.models.rule_set import DEFAULT_LINE_WIDTH
from subedit.infrastructure import ALL_RULES, DEFAULT_PARSER


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = REPOSITORY_ROOT / 'tests' / 'fixtures'
SUFFIXES = {'python': '.py', 'typescript': '.ts', 'tsx': '.tsx', 'javascript': '.js', 'markdown': '.md'}


def document(text: str, language_id: str = 'python') -> Document:
    """A document in memory, named for its language so the parser reads it as one."""
    return Document(uri=f'file:///a{SUFFIXES[language_id]}', text=text, language_id=language_id)


def markdown(text: str) -> Document:
    """A Markdown document in memory."""
    return document(text, 'markdown')


def rule_ids(rules: typing.Iterable[Rule[typing.Any]]) -> frozenset[str]:
    """The IDs of the rules given, to enable exactly those."""
    return frozenset(rule.metadata.rule_id for rule in rules)


def rule_set(
    enabled: typing.Iterable[str] = rule_ids(ALL_RULES),
    width: int = DEFAULT_LINE_WIDTH,
    settings: typing.Mapping[str, RuleSettings] | None = None,
) -> RuleSet:
    """A rule set enabling the IDs given, every native rule by default, with each rule's settings by its ID."""
    return RuleSet(enabled_rule_ids=frozenset(enabled), line_width=width, settings=settings or {})


def lint(subject: Document, rules: RuleSet | None = None, engine: tuple[Rule[typing.Any], ...] = ALL_RULES) -> Report:
    """What the linter reports on a document, under every native rule unless told otherwise."""
    return Linter(DEFAULT_PARSER, RuleEngine(engine)).run(subject, rules or rule_set())


def found(report: Report) -> list[str]:
    """The rule ID of each finding, in the order reported."""
    return [diagnostic.rule_id for diagnostic in report.diagnostics]


def fixed(subject: Document, rules: RuleSet | None = None, engine: tuple[Rule[typing.Any], ...] = ALL_RULES) -> str:
    """The document's text once the fixer has applied every mechanical fix."""
    return Fixer(Linter(DEFAULT_PARSER, RuleEngine(engine))).run(subject, rules or rule_set()).document.text


def first_fix_applied(text: str, report: Report) -> str:
    """The text with only the first mechanical fix applied, to check one rule's edit on its own."""
    edits = tuple(edit for item in report.mechanical if item.fix for edit in item.fix.edits)
    return apply_edits(text, edits[:1]) if edits else text


def edit(start: int = 0, end: int = 1, new_text: str = 'x') -> TextEdit:
    """An edit replacing the bytes from start to end."""
    return TextEdit(SourceRange(start, end), new_text)


class Project:
    """A throwaway repository on disk, so a test writes only the files it is about."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root

    def write(self, name: str, body: str) -> pathlib.Path:
        """Write a file under the repository, with any folders it needs, and return its path."""
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding='utf-8')
        return path
