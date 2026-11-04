import typing

import pydantic

from ...domain.models.diagnostic import SEVERITY_BY_NAME, Severity


class ConfigError(ValueError):
    """A config subedit cannot read as written, which it reports rather than run on defaults the project never chose."""


_SeverityName = typing.Literal['error', 'warning', 'suggestion']


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


_RuleEntry = typing.Annotated[
    typing.Literal['off', 'error', 'warning', 'suggestion'] | RuleTable, pydantic.Field(union_mode='left_to_right')
]


class SubeditSection(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True, populate_by_name=True, extra='forbid')

    # Left unset, the width falls back to the language's own default.
    line_width: int | None = pydantic.Field(default=None, alias='line-width', gt=0)
    exclude: tuple[str, ...] = ()
    code_blocks: bool = pydantic.Field(default=False, alias='code-blocks')
    # Each is written with its period, as in Dept., since the case and the period are matched as written.
    abbreviations: tuple[str, ...] = ()

    @pydantic.field_validator('abbreviations')
    @classmethod
    def _written_with_a_period(cls, abbreviations: tuple[str, ...]) -> tuple[str, ...]:
        for abbreviation in abbreviations:
            if len(abbreviation) < 2 or not abbreviation.endswith('.') or ' ' in abbreviation:
                raise ValueError(f'{abbreviation!r} must be one word ending in its period, as in Dept.')
        return abbreviations


class ConfigFile(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True, extra='forbid')

    subedit: SubeditSection = pydantic.Field(default_factory=SubeditSection)
    rules: dict[str, _RuleEntry] = pydantic.Field(default_factory=dict)

    @classmethod
    def parse(cls, raw: typing.Mapping[str, object]) -> 'ConfigFile':
        try:
            return cls.model_validate(raw)
        except pydantic.ValidationError as error:
            details = [detail for detail in error.errors() if _matches_what_was_written(detail)]
            raise ConfigError('; '.join(_describe(detail) for detail in details)) from None


# A rule entry is a level or a table, and pydantic reports both branches, so only the one written stays.
def _matches_what_was_written(detail: typing.Any) -> bool:
    branches = [str(part) for part in detail['loc'] if str(part).startswith('literal[') or part == 'RuleTable']
    if not branches:
        return True
    if branches[0] == 'RuleTable':
        return detail['type'] != 'model_type'
    return not isinstance(detail['input'], dict)


def _describe(detail: typing.Any) -> str:
    location = '.'.join(
        str(part) for part in detail['loc'] if not str(part).startswith('literal[') and part != 'RuleTable'
    )
    message = 'is not a setting subedit knows' if detail['type'] == 'extra_forbidden' else detail['msg']
    # A validator's own sentence comes after the prefix pydantic puts on it.
    message = message.removeprefix('Value error, ')
    return f'{location}: {message}' if location else message
