import typing

import pydantic

from ...domain.models.diagnostic import SEVERITY_BY_NAME, Severity


_SeverityName = typing.Literal['error', 'warning', 'suggestion']
# The names pydantic gives the table branch of an entry that is a word or a table.
_TABLE_BRANCHES = ('RuleTable', 'SurfaceSection')


class ConfigError(ValueError):
    """A config subedit cannot read as written, which it reports rather than run on defaults the project never chose."""


class RuleTable(pydantic.BaseModel):
    # A rule's options depend on the rule, so the config source checks them against what each rule declares.
    model_config = pydantic.ConfigDict(extra='allow', frozen=True)

    severity: _SeverityName | None = None

    @property
    def resolved_severity(self) -> Severity | None:
        return SEVERITY_BY_NAME[self.severity] if self.severity else None

    @property
    def options(self) -> dict[str, object]:
        return dict(self.__pydantic_extra__ or {})


RuleEntry = typing.Annotated[
    typing.Literal['off', 'error', 'warning', 'suggestion'] | RuleTable, pydantic.Field(union_mode='left_to_right')
]


class SubeditSection(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True, populate_by_name=True, extra='forbid')

    # Left unset, the width falls back to the language's own default.
    line_width: int | None = pydantic.Field(default=None, alias='line-width', gt=0)
    exclude: tuple[str, ...] = ()
    # Each is written with its period, as in Dept., since the case and the period are matched as written.
    abbreviations: tuple[str, ...] = ()

    @pydantic.field_validator('abbreviations')
    @classmethod
    def _written_with_a_period(cls, abbreviations: tuple[str, ...]) -> tuple[str, ...]:
        for abbreviation in abbreviations:
            if len(abbreviation) < 2 or not abbreviation.endswith('.') or ' ' in abbreviation:
                raise ValueError(f'{abbreviation!r} must be one word ending in its period, as in Dept.')
        return abbreviations


class SurfaceSection(pydantic.BaseModel):
    """What a project sets for one surface, such as commit-messages, over what it sets for every surface."""

    model_config = pydantic.ConfigDict(frozen=True, populate_by_name=True, extra='forbid')

    line_width: int | None = pydantic.Field(default=None, alias='line-width', gt=0)
    # A document embedded in one of the surface's, such as a Markdown code block, is often an example,
    # so it is read only when the project asks.
    code_blocks: bool | None = pydantic.Field(default=None, alias='code-blocks')
    rules: dict[str, RuleEntry] = pydantic.Field(default_factory=dict)


# A surface is switched off as a rule is, with "off", or set apart with a table of its own.
SurfaceEntry = typing.Annotated[typing.Literal['off'] | SurfaceSection, pydantic.Field(union_mode='left_to_right')]


class ConfigFile(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True, extra='forbid')

    subedit: SubeditSection = pydantic.Field(default_factory=SubeditSection)
    rules: dict[str, RuleEntry] = pydantic.Field(default_factory=dict)
    surfaces: dict[str, SurfaceEntry] = pydantic.Field(default_factory=dict)

    @property
    def surface_sections(self) -> dict[str, SurfaceSection]:
        """The surfaces the project sets apart with a table, leaving out those it switches off."""
        return {name: entry for name, entry in self.surfaces.items() if isinstance(entry, SurfaceSection)}

    @property
    def off_surfaces(self) -> frozenset[str]:
        return frozenset(name for name, entry in self.surfaces.items() if entry == 'off')

    @classmethod
    def parse(cls, raw: typing.Mapping[str, object]) -> 'ConfigFile':
        settings = raw.get('subedit')
        if isinstance(settings, dict) and 'code-blocks' in settings:
            raise ConfigError(
                'subedit.code-blocks: moved to [surfaces.markdown], as code-blocks = true, '
                'since it belongs to the surface whose code blocks it reads'
            )
        try:
            return cls.model_validate(raw)
        except pydantic.ValidationError as error:
            details = [detail for detail in error.errors() if _matches_what_was_written(detail)]
            raise ConfigError('; '.join(_describe(detail) for detail in details)) from None


# A rule or surface entry is a word or a table, and pydantic reports both branches, so only the one written stays.
def _matches_what_was_written(detail: typing.Any) -> bool:
    branches = [str(part) for part in detail['loc'] if _is_branch(part)]
    if not branches:
        return True
    if branches[0] in _TABLE_BRANCHES:
        return detail['type'] != 'model_type'
    return not isinstance(detail['input'], dict)


def _describe(detail: typing.Any) -> str:
    location = '.'.join(str(part) for part in detail['loc'] if not _is_branch(part))
    message = 'is not a setting subedit knows' if detail['type'] == 'extra_forbidden' else detail['msg']
    # A validator's own sentence comes after the prefix pydantic puts on it.
    message = message.removeprefix('Value error, ')
    return f'{location}: {message}' if location else message


def _is_branch(part: object) -> bool:
    return str(part).startswith('literal[') or part in _TABLE_BRANCHES
