import importlib.util
import pathlib
import shutil
import subprocess
import sys
import typing

import pydantic

from ...domain.models.diagnostic import SEVERITY_BY_NAME, Diagnostic, Fix, Severity
from ...domain.models.document import Document
from ...domain.models.position import Position, SourceRange
from ...domain.models.prose import code_spans
from ...domain.ports.external_linter import ExternalLinter
from .source_path import as_known_path


TIMEOUT_SECONDS = 30
# The first run of the vale extra downloads the binary, which a slow link can take minutes over.
PREPARE_TIMEOUT_SECONDS = 900
BUNDLED_CONFIG = pathlib.Path(__file__).resolve().parents[2] / 'vale' / 'vale.ini'
# Vale exits with this code when its own search finds no config.
NO_CONFIG_CODE = 'E100'
# The vale extra's placeholder is smaller than this until the real binary replaces it.
PLACEHOLDER_BYTES = 1000


class ValeAlert(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True, extra='ignore')

    check: str = pydantic.Field(alias='Check')
    message: str = pydantic.Field(alias='Message')
    line: int = pydantic.Field(alias='Line', ge=1)
    span: tuple[int, int] = pydantic.Field(default=(1, 1), alias='Span')
    severity: str = pydantic.Field(default='error', alias='Severity')

    @property
    def resolved_severity(self) -> Severity:
        return SEVERITY_BY_NAME.get(self.severity, Severity.ERROR)


class ValeReport(pydantic.RootModel[dict[str, list[ValeAlert]]]):
    @classmethod
    def parse(cls, payload: str) -> tuple[ValeAlert, ...]:
        try:
            report = cls.model_validate_json(payload or '{}')
        except pydantic.ValidationError:
            return ()
        return tuple(alert for alerts in report.root.values() for alert in alerts)


class ValeLinter(ExternalLinter):
    name = 'vale'

    def __init__(
        self,
        executable: str | None = None,
        fallback_config: pathlib.Path = BUNDLED_CONFIG,
        suffix_aliases: typing.Mapping[str, str] | None = None,
    ) -> None:
        self._executable = executable or _default_executable()
        self._suffix_aliases = dict(suffix_aliases or {})
        self._fallback_config = fallback_config
        self._needs_fallback = False

    def is_available(self) -> bool:
        return shutil.which(self._executable) is not None and _launcher_is_ready()

    def prepare(self) -> None:
        """Let the vale extra finish its download, with progress left on stderr so a waiting command shows why."""
        if _launcher_is_ready() or shutil.which(self._executable) is None:
            return
        try:
            subprocess.run(  # noqa: S603
                [self._executable, '--version'],
                stdout=subprocess.DEVNULL,
                check=False,
                timeout=PREPARE_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired):
            return

    def run(self, document: Document) -> tuple[Diagnostic, ...]:
        if not self.is_available():
            return ()
        # The text goes in on stdin, because during a fix it is ahead of what the file on disk holds.
        # The path still selects the config sections, and Vale matches them exactly as for a file.
        source_path = as_known_path(document.uri.removeprefix('file://'), self._suffix_aliases)
        if not self._needs_fallback:
            process = self._run_vale(document, source_path)
            if process is None:
                return ()
            if NO_CONFIG_CODE not in process.stderr:
                return self._decode(document, process.stdout)
            # A repo with no config of its own gets the bundled one, and every later file skips the miss.
            self._needs_fallback = True
        process = self._run_vale(document, source_path, f'--config={self._fallback_config}')
        return () if process is None else self._decode(document, process.stdout)

    def _run_vale(
        self, document: Document, source_path: str, *extra_args: str
    ) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(  # noqa: S603
                [self._executable, '--no-exit', '--output=JSON', *extra_args, f'--path={source_path}'],
                input=document.text,
                capture_output=True,
                text=True,
                check=False,
                timeout=TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

    def _decode(self, document: Document, payload: str) -> tuple[Diagnostic, ...]:
        diagnostics: list[Diagnostic] = []
        for alert in ValeReport.parse(payload):
            diagnostic = self._to_diagnostic(document, alert)
            if diagnostic is not None:
                diagnostics.append(diagnostic)
        return tuple(diagnostics)

    def _to_diagnostic(self, document: Document, alert: ValeAlert) -> Diagnostic | None:
        start_column, end_column = alert.span
        if _inside_code_span(document, alert.line, start_column):
            return None
        try:
            start_offset = document.positions.to_offset(Position(alert.line - 1, start_column - 1))
            end_offset = document.positions.to_offset(Position(alert.line - 1, end_column))
        except ValueError:
            return None
        return Diagnostic(
            rule_id=alert.check,
            range=SourceRange(start_offset, max(start_offset, end_offset)),
            message=alert.message,
            severity=alert.resolved_severity,
            fix=Fix.rewrite(),
            source=self.name,
        )


# Vale ignores a code span only in markup, so in a source file it reads the code inside one as prose.
def _inside_code_span(document: Document, line: int, column: int) -> bool:
    lines = document.text.split('\n')
    if not 0 < line <= len(lines):
        return False
    return any(start < column <= end for start, end in code_spans(lines[line - 1]))


# The vale extra installs its launcher beside this interpreter, which uvx does not put on PATH.
def _default_executable() -> str:
    return shutil.which('vale', path=str(pathlib.Path(sys.executable).parent)) or 'vale'


# The vale extra downloads the real binary on its first run, in place of a small placeholder.
# Until that lands, Vale counts as missing, so an edit never waits on a download.
def _launcher_is_ready() -> bool:
    spec = importlib.util.find_spec('vale')
    if spec is None or spec.origin is None:
        return True
    placeholder = pathlib.Path(spec.origin).parent / 'vale_bin'
    try:
        return placeholder.stat().st_size >= PLACEHOLDER_BYTES
    except OSError:
        return True
