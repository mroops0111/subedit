import dataclasses
import fnmatch
import pathlib
import tomllib
import typing

from ...domain.models.diagnostic import RuleMetadata
from ...domain.models.file_type import FileType
from ...domain.models.rule_set import DEFAULT_LINE_WIDTH, RuleSet, RuleSettings
from .config_schema import ConfigError, ConfigFile, RuleEntry, RuleTable
from .formatter_width import FormatterWidths


CONFIG_NAME = 'subedit.toml'
_PYPROJECT_NAME = 'pyproject.toml'
# The tables that sit beside [tool.subedit]'s own settings rather than among them.
_TABLES = ('rules', 'surfaces')


class TomlConfigSource:
    """Reads subedit.toml or the tool table in pyproject.toml, found by walking up from the file checked.

    A config it cannot read as written raises a ConfigError naming the file, rather than leave the project on defaults.
    """

    def __init__(
        self,
        rules: tuple[RuleMetadata, ...],
        formatter_widths: FormatterWidths | None = None,
        fallback_width: int = DEFAULT_LINE_WIDTH,
        file_types: tuple[FileType, ...] = (),
    ) -> None:
        self._rules = {metadata.rule_id: metadata for metadata in rules}
        self._available_rule_ids = tuple(self._rules)
        self._formatter_widths = formatter_widths or FormatterWidths({})
        self._fallback_width = fallback_width
        self._file_types = file_types

    def resolve(self, path: str) -> RuleSet:
        config_file = self._read(path)
        if config_file is None:
            return self.defaults(path)
        return self._to_rule_set(config_file, path)

    def defaults(self, path: str = '') -> RuleSet:
        return RuleSet(enabled_rule_ids=frozenset(self._available_rule_ids), line_width=self.default_width(path))

    def default_width(self, path: str) -> int:
        """The width a file gets when subedit's config sets none.

        A commit message takes the width its own convention sets. Any other file takes its formatter's, if it has one.
        """
        file_type = self._file_type_for(path)
        if file_type is not None and file_type.line_width is not None:
            return file_type.line_width
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
            'subedit': {name: setting for name, setting in tool_section.items() if name not in _TABLES},
            **{name: tool_section[name] for name in _TABLES if name in tool_section},
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
        # A pyproject.toml that does not parse shows no opt in, and its mistake belongs to the project's other tools.
        try:
            raw_table = _load(config_path)
        except ConfigError:
            return False
        tools = raw_table.get('tool') if raw_table else None
        return isinstance(tools, dict) and 'subedit' in tools

    def _check_options(self, config_file: ConfigFile) -> None:
        known_surfaces = sorted({file_type.surface for file_type in self._file_types})
        for surface in config_file.surfaces:
            if known_surfaces and surface not in known_surfaces:
                raise ConfigError(
                    f'surfaces.{surface}: is not a surface subedit reads, it reads {", ".join(known_surfaces)}'
                )
        self._check_rules('rules', config_file.rules)
        for surface, section in config_file.surface_tables.items():
            self._check_rules(f'surfaces.{surface}.rules', section.rules)

    # A rule subedit does not define belongs to a delegated tool, whose options it cannot know.
    # A delegated tool names its rules Style.Rule, as Vale and AutoCorrect do,
    # so a name with no dot that subedit does not define is a mistake, such as a rule's old name.
    def _check_rules(self, table: str, rules: typing.Mapping[str, RuleEntry]) -> None:
        for rule_id, rule_entry in rules.items():
            metadata = self._rules.get(rule_id)
            if metadata is None and '.' not in rule_id:
                raise ConfigError(
                    f'{table}.{rule_id}: is not a rule subedit defines, and a Vale rule is named Style.Rule'
                )
            if metadata is None or not isinstance(rule_entry, RuleTable):
                continue
            declared = {option.name: option for option in metadata.options}
            for name, value in rule_entry.options.items():
                option = declared.get(name)
                if option is None:
                    takes = f'it takes {", ".join(declared)}' if declared else 'it takes none'
                    raise ConfigError(f'{table}.{rule_id}.{name}: is not an option of {rule_id}, {takes}')
                if not option.accepts(value):
                    raise ConfigError(f'{table}.{rule_id}.{name}: must be {option.expected}')

    # Each option of a native rule converts its own value, and a delegated tool's options pass through as read.
    def _converted(self, rule_id: str, options: typing.Mapping[str, object]) -> dict[str, object]:
        metadata = self._rules.get(rule_id)
        if metadata is None:
            return dict(options)
        declared = {option.name: option for option in metadata.options}
        return {name: declared[name].convert(value) for name, value in options.items()}

    # A width set for the file's surface wins, then a width the file's own convention sets,
    # since a project's line-width is chosen for its code.
    def _width(self, config_file: ConfigFile, path: str) -> int:
        file_type = self._file_type_for(path)
        if file_type is not None:
            surface = config_file.surface_tables.get(file_type.surface)
            if surface is not None and surface.line_width is not None:
                return surface.line_width
            if file_type.line_width is not None:
                return file_type.line_width
        return config_file.subedit.line_width or self.default_width(path)

    def _file_type_for(self, path: str) -> FileType | None:
        return next((file_type for file_type in self._file_types if file_type.matches(pathlib.Path(path))), None)

    def _to_rule_set(self, config_file: ConfigFile, path: str) -> RuleSet:
        project_rules = self._rule_set(config_file, config_file.rules, self._width(config_file, path))
        by_language: dict[str, RuleSet] = {}
        for file_type in self._file_types:
            if file_type.surface in config_file.off_surfaces:
                by_language[file_type.language_id] = RuleSet(enabled_rule_ids=frozenset(), is_off=True)
        for surface, section in config_file.surface_tables.items():
            rules = _overlaid(config_file.rules, section.rules)
            for file_type in self._file_types:
                if file_type.surface == surface:
                    width = section.line_width or file_type.line_width or project_rules.line_width
                    by_language[file_type.language_id] = self._rule_set(
                        config_file, rules, width, reads_embedded=bool(section.code_blocks)
                    )
        return dataclasses.replace(project_rules, by_language=by_language)

    def _rule_set(
        self,
        config_file: ConfigFile,
        rules: typing.Mapping[str, RuleEntry],
        line_width: int,
        *,
        reads_embedded: bool = False,
    ) -> RuleSet:
        enabled_ids = set(self._available_rule_ids)
        disabled_external_ids: set[str] = set()
        settings: dict[str, RuleSettings] = {}

        # A name subedit does not define belongs to a delegated tool, such as subedit.Semicolon from Vale.
        for rule_id, rule_entry in rules.items():
            if rule_entry == 'off':
                if rule_id in self._available_rule_ids:
                    enabled_ids.discard(rule_id)
                else:
                    disabled_external_ids.add(rule_id)
            elif isinstance(rule_entry, RuleTable):
                options = self._converted(rule_id, rule_entry.options)
                settings[rule_id] = RuleSettings(severity=rule_entry.resolved_severity, options=options)
            else:
                settings[rule_id] = RuleSettings(severity=RuleTable(severity=rule_entry).resolved_severity)

        return RuleSet(
            enabled_rule_ids=frozenset(enabled_ids),
            settings=settings,
            line_width=line_width,
            disabled_external_ids=frozenset(disabled_external_ids),
            reads_embedded=reads_embedded,
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


# A surface's entry replaces the project's for that rule, except that a table's options join the project's table.
def _overlaid(
    rules: typing.Mapping[str, RuleEntry], surface_rules: typing.Mapping[str, RuleEntry]
) -> dict[str, RuleEntry]:
    merged = dict(rules)
    for rule_id, entry in surface_rules.items():
        base = merged.get(rule_id)
        if isinstance(entry, RuleTable) and isinstance(base, RuleTable):
            entry = RuleTable.model_validate(
                {'severity': entry.severity or base.severity, **base.options, **entry.options}
            )
        merged[rule_id] = entry
    return merged
