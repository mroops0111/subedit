import dataclasses
import json
import pathlib
import re
import tomllib
import typing


# A string is matched first, so a URL inside one, as a $schema value holds, keeps its slashes.
_JSON_COMMENT = re.compile(r'("(?:\\.|[^"\\])*")|//[^\n]*|/\*.*?\*/', re.DOTALL)
_TRAILING_COMMA = re.compile(r',(\s*[}\]])')


@dataclasses.dataclass(frozen=True, slots=True)
class WidthSetting:
    """Where a formatter keeps its line width, such as line-length under [tool.ruff] in pyproject.toml."""

    file_name: str
    key_path: tuple[str, ...]

    def read(self, directory: pathlib.Path) -> int | None:
        config_path = directory / self.file_name
        if not config_path.is_file():
            return None
        try:
            text = config_path.read_text(encoding='utf-8')
        except OSError:
            return None
        return self._width_in(self._parse(text, config_path.suffix))

    def _parse(self, text: str, suffix: str) -> object:
        if suffix == '.toml':
            try:
                return tomllib.loads(text)
            except tomllib.TOMLDecodeError:
                return None
        for candidate in (text, _without_comments(text)):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        return self._parse_flat(text)

    # A YAML .prettierrc holds a top-level key on a line of its own.
    def _parse_flat(self, text: str) -> object:
        if len(self.key_path) != 1:
            return None
        (key,) = self.key_path
        found = re.search(rf'^{re.escape(key)}\s*:\s*(\d+)\s*$', text, re.MULTILINE)
        return {key: int(found.group(1))} if found else None

    def _width_in(self, table: object) -> int | None:
        for key in self.key_path:
            if not isinstance(table, dict):
                return None
            table = typing.cast(dict[str, object], table).get(key)
        return table if isinstance(table, int) and not isinstance(table, bool) and table > 0 else None


class FormatterWidths:
    """The line width a project's own formatter sets, found the way the formatter finds its config.

    The search climbs from the file toward the root, and the nearest directory that sets a width wins.
    A formatter left at its own default sets nothing here, so the width falls back to subedit's default.
    """

    def __init__(self, settings_by_suffix: typing.Mapping[str, tuple[WidthSetting, ...]]) -> None:
        self._settings_by_suffix = dict(settings_by_suffix)
        self._widths: dict[tuple[pathlib.Path, tuple[WidthSetting, ...]], int | None] = {}

    def width_for(self, path: str) -> int | None:
        settings = self._settings_by_suffix.get(pathlib.Path(path).suffix)
        if not settings:
            return None
        start = pathlib.Path(path)
        directory = (start if start.is_dir() else start.parent).resolve()
        if (directory, settings) not in self._widths:
            self._widths[directory, settings] = self._width_from(directory, settings)
        return self._widths[directory, settings]

    def _width_from(self, directory: pathlib.Path, settings: tuple[WidthSetting, ...]) -> int | None:
        for candidate in (directory, *directory.parents):
            for setting in settings:
                width = setting.read(candidate)
                if width is not None:
                    return width
        return None


def _without_comments(text: str) -> str:
    """JSON with the comments and trailing commas that JSONC allows taken out, as biome.jsonc writes it."""
    return _TRAILING_COMMA.sub(r'\1', _JSON_COMMENT.sub(lambda found: found.group(1) or '', text))
