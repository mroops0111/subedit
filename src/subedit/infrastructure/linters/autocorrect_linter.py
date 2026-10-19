import pathlib
import typing

import autocorrect_py

from ...domain.models.diagnostic import Diagnostic, Fix, Severity
from ...domain.models.document import Document
from ...domain.models.position import Position, SourceRange
from ...domain.models.text import TextEdit
from ...domain.ports.external_linter import ExternalLinter
from .source_path import as_known_path


RULE_ID = 'autocorrect/spacing'
CONFIG_PATH = pathlib.Path('.autocorrectrc')


class AutoCorrectLinter(ExternalLinter):
    name = 'autocorrect'

    def __init__(
        self, config_path: pathlib.Path = CONFIG_PATH, suffix_aliases: typing.Mapping[str, str] | None = None
    ) -> None:
        self._config_path = config_path
        self._suffix_aliases = dict(suffix_aliases or {})
        self._config_loaded = False

    def is_available(self) -> bool:
        """Always true, since AutoCorrect arrives as a Python dependency rather than a separate install."""
        return True

    def run(self, document: Document) -> tuple[Diagnostic, ...]:
        """Diff AutoCorrect's rewrite of the text into one targeted edit per changed line.

        The path only tells AutoCorrect which file type to parse, so it need not exist on disk.
        """
        self._load_config()
        # Its grammar gives up on a large file, and one file it cannot read must not stop the run.
        try:
            corrected_text = autocorrect_py.format_for(
                document.text, as_known_path(document.uri.removeprefix('file://'), self._suffix_aliases)
            )
        except ValueError:
            return ()
        if corrected_text == document.text:
            return ()
        return self._diff_lines(document, corrected_text)

    # The command line tool reads .autocorrectrc from the working directory, so the library does the same.
    # The config is global to the library, so it loads once.
    def _load_config(self) -> None:
        if self._config_loaded:
            return
        self._config_loaded = True
        try:
            config_text = self._config_path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            return
        autocorrect_py.load_config(config_text)  # pyright: ignore[reportAttributeAccessIssue]

    def _diff_lines(self, document: Document, corrected_text: str) -> tuple[Diagnostic, ...]:
        original_lines = document.text.splitlines(keepends=True)
        corrected_lines = corrected_text.splitlines(keepends=True)
        if len(original_lines) != len(corrected_lines):
            return ()
        diagnostics: list[Diagnostic] = []
        for index, (original, fixed) in enumerate(zip(original_lines, corrected_lines, strict=True)):
            if original == fixed:
                continue
            start_offset = document.positions.to_offset(Position(index, 0))
            end_offset = start_offset + len(original.rstrip('\n').encode('utf-8'))
            diagnostics.append(
                Diagnostic(
                    rule_id=RULE_ID,
                    range=SourceRange(start_offset, end_offset),
                    message='Spacing or punctuation between CJK and Latin text needs correcting.',
                    severity=Severity.ERROR,
                    fix=Fix.targeted(TextEdit(SourceRange(start_offset, end_offset), fixed.rstrip('\n'))),
                    source=self.name,
                )
            )
        return tuple(diagnostics)
