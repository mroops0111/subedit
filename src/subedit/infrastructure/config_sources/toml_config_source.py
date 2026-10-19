import fnmatch
import pathlib
import tomllib

from ...domain.models.rule_set import DEFAULT_LINE_WIDTH, RuleSet, RuleSettings
from .config_schema import ConfigFile, RuleTable
from .formatter_width import FormatterWidths


CONFIG_NAME = 'subedit.toml'
PYPROJECT_NAME = 'pyproject.toml'


class TomlConfigSource:
    def __init__(
        self,
        available_rule_ids: tuple[str, ...],
        formatter_widths: FormatterWidths | None = None,
        fallback_width: int = DEFAULT_LINE_WIDTH,
    ) -> None:
        self._available_rule_ids = available_rule_ids
        self._formatter_widths = formatter_widths or FormatterWidths({})
        self._fallback_width = fallback_width

    def resolve(self, path: str) -> RuleSet:
        config_file = self._read(path)
        if config_file is None:
            return self.defaults(path)
        return self._to_rule_set(config_file, path)

    def defaults(self, path: str = '') -> RuleSet:
        return RuleSet(enabled_rule_ids=frozenset(self._available_rule_ids), line_width=self.default_width(path))

    def default_width(self, path: str) -> int:
        """The width a file gets when subedit's config sets none, which the project's formatter sets if it has one."""
        formatter_width = self._formatter_widths.width_for(path)
        return self._fallback_width if formatter_width is None else formatter_width

    def exclude_patterns(self, path: str) -> tuple[str, ...]:
        config_file = self._read(path)
        return config_file.subedit.exclude if config_file else ()

    def is_excluded(self, target: pathlib.Path, root: pathlib.Path, patterns: tuple[str, ...]) -> bool:
        try:
            relative = target.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            relative = target.resolve().as_posix()
        return any(fnmatch.fnmatch(relative, pattern) for pattern in patterns)

    def root_for(self, path: str) -> pathlib.Path:
        config_path = self._locate(pathlib.Path(path))
        return config_path.parent if config_path else pathlib.Path.cwd()

    def _read(self, path: str) -> ConfigFile | None:
        config_path = self._locate(pathlib.Path(path))
        if config_path is None:
            return None
        try:
            raw_table = tomllib.loads(config_path.read_text(encoding='utf-8'))
        except (OSError, tomllib.TOMLDecodeError):
            return None
        if config_path.name == PYPROJECT_NAME:
            raw_table = self._reshape_pyproject(raw_table)
            if raw_table is None:
                return None
        return ConfigFile.parse(raw_table)

    def _reshape_pyproject(self, raw_table: dict[str, object]) -> dict[str, object] | None:
        tools = raw_table.get('tool')
        tool_section = tools.get('subedit') if isinstance(tools, dict) else None
        if not isinstance(tool_section, dict):
            return None
        return {
            'subedit': {name: setting for name, setting in tool_section.items() if name != 'rules'},
            'rules': tool_section.get('rules', {}),
        }

    def _locate(self, start: pathlib.Path) -> pathlib.Path | None:
        base = start if start.is_dir() else start.parent
        for directory in (base.resolve(), *base.resolve().parents):
            for name in (CONFIG_NAME, PYPROJECT_NAME):
                config_path = directory / name
                if config_path.is_file() and self._carries_settings(config_path):
                    return config_path
        return None

    def _carries_settings(self, config_path: pathlib.Path) -> bool:
        if config_path.name != PYPROJECT_NAME:
            return True
        try:
            tools = tomllib.loads(config_path.read_text(encoding='utf-8')).get('tool')
        except (OSError, tomllib.TOMLDecodeError):
            return False
        return isinstance(tools, dict) and 'subedit' in tools

    def _to_rule_set(self, config_file: ConfigFile, path: str) -> RuleSet:
        enabled_ids = set(self._available_rule_ids)
        disabled_external_ids: set[str] = set()
        settings: dict[str, RuleSettings] = {}

        # A name subedit does not define belongs to a delegated tool, such as subedit.Semicolon from Vale.
        for rule_id, rule_entry in config_file.rules.items():
            if rule_entry is False or rule_entry == 'off':
                if rule_id in self._available_rule_ids:
                    enabled_ids.discard(rule_id)
                else:
                    disabled_external_ids.add(rule_id)
            elif isinstance(rule_entry, RuleTable):
                settings[rule_id] = RuleSettings(severity=rule_entry.resolved_severity, options=rule_entry.options)
            elif isinstance(rule_entry, str):
                settings[rule_id] = RuleSettings(severity=RuleTable(severity=rule_entry).resolved_severity)

        return RuleSet(
            enabled_rule_ids=frozenset(enabled_ids),
            settings=settings,
            line_width=config_file.subedit.line_width or self.default_width(path),
            disabled_external_ids=frozenset(disabled_external_ids),
        )
