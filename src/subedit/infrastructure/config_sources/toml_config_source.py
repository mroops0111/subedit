import fnmatch
import pathlib
import tomllib

from ...domain.models.diagnostic import RuleMetadata
from ...domain.models.rule_set import DEFAULT_LINE_WIDTH, RuleSet, RuleSettings
from .config_schema import ConfigError, ConfigFile, RuleTable
from .formatter_width import FormatterWidths


CONFIG_NAME = 'subedit.toml'
_PYPROJECT_NAME = 'pyproject.toml'


class TomlConfigSource:
    """Reads subedit.toml or the tool table in pyproject.toml, found by walking up from the file checked.

    A config it cannot read as written raises a ConfigError naming the file, rather than leave the project on defaults.
    """

    def __init__(
        self,
        rules: tuple[RuleMetadata, ...],
        formatter_widths: FormatterWidths | None = None,
        fallback_width: int = DEFAULT_LINE_WIDTH,
    ) -> None:
        self._rules = {metadata.rule_id: metadata for metadata in rules}
        self._available_rule_ids = tuple(self._rules)
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

    def is_adopted(self, path: str) -> bool:
        """Whether a subedit.toml or a pyproject.toml with [tool.subedit] covers the path, as a project opts in."""
        return self._locate(pathlib.Path(path)) is not None

    def root_for(self, path: str) -> pathlib.Path:
        config_path = self._locate(pathlib.Path(path))
        return config_path.parent if config_path else pathlib.Path.cwd()

    def _read(self, path: str) -> ConfigFile | None:
        config_path = self._locate(pathlib.Path(path))
        if config_path is None:
            return None
        raw_table = _load(config_path)
        if raw_table is None:
            return None
        if config_path.name == _PYPROJECT_NAME:
            raw_table = self._reshape_pyproject(raw_table)
            if raw_table is None:
                return None
        try:
            config_file = ConfigFile.parse(raw_table)
            self._check_options(config_file)
        except ConfigError as error:
            raise ConfigError(f'{config_path}: {error}') from None
        return config_file

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
            for name in (CONFIG_NAME, _PYPROJECT_NAME):
                config_path = directory / name
                if config_path.is_file() and self._carries_settings(config_path):
                    return config_path
        return None

    def _carries_settings(self, config_path: pathlib.Path) -> bool:
        if config_path.name != _PYPROJECT_NAME:
            return True
        raw_table = _load(config_path)
        tools = raw_table.get('tool') if raw_table else None
        return isinstance(tools, dict) and 'subedit' in tools

    def _check_options(self, config_file: ConfigFile) -> None:
        # A rule subedit does not define belongs to a delegated tool, whose options it cannot know.
        # A delegated tool names its rules Style.Rule, as Vale and AutoCorrect do,
        # so a name with no dot that subedit does not define is a mistake, such as a rule's old name.
        for rule_id, rule_entry in config_file.rules.items():
            metadata = self._rules.get(rule_id)
            if metadata is None and '.' not in rule_id:
                raise ConfigError(
                    f'rules.{rule_id}: is not a rule subedit defines, and a Vale rule is named Style.Rule'
                )
            if metadata is None or not isinstance(rule_entry, RuleTable):
                continue
            declared = {option.name: option for option in metadata.options}
            for name, value in rule_entry.options.items():
                option = declared.get(name)
                if option is None:
                    takes = f'it takes {", ".join(declared)}' if declared else 'it takes none'
                    raise ConfigError(f'rules.{rule_id}.{name}: is not an option of {rule_id}, {takes}')
                if not option.accepts(value):
                    raise ConfigError(f'rules.{rule_id}.{name}: must be {option.expected}')

    def _to_rule_set(self, config_file: ConfigFile, path: str) -> RuleSet:
        enabled_ids = set(self._available_rule_ids)
        disabled_external_ids: set[str] = set()
        settings: dict[str, RuleSettings] = {}

        # A name subedit does not define belongs to a delegated tool, such as subedit.Semicolon from Vale.
        for rule_id, rule_entry in config_file.rules.items():
            if rule_entry == 'off':
                if rule_id in self._available_rule_ids:
                    enabled_ids.discard(rule_id)
                else:
                    disabled_external_ids.add(rule_id)
            elif isinstance(rule_entry, RuleTable):
                options = {name: _normalized(value) for name, value in rule_entry.options.items()}
                settings[rule_id] = RuleSettings(severity=rule_entry.resolved_severity, options=options)
            else:
                settings[rule_id] = RuleSettings(severity=RuleTable(severity=rule_entry).resolved_severity)

        return RuleSet(
            enabled_rule_ids=frozenset(enabled_ids),
            settings=settings,
            line_width=config_file.subedit.line_width or self.default_width(path),
            disabled_external_ids=frozenset(disabled_external_ids),
            reads_embedded=config_file.subedit.code_blocks,
            abbreviations=frozenset(config_file.subedit.abbreviations),
        )


# A file that cannot be read is no config, but one that does not parse is a mistake the project should see.
def _load(config_path: pathlib.Path) -> dict[str, object] | None:
    try:
        text = config_path.read_text(encoding='utf-8')
    except OSError:
        return None
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f'{config_path}: {error}') from None


# TOML reads an array as a list, while an option's default is a tuple, so a rule always meets the same type.
def _normalized(value: object) -> object:
    return tuple(value) if isinstance(value, list) else value
