import typing

import pydantic

from ...domain.models.diagnostic import SEVERITY_BY_NAME, Severity


class RuleTable(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra='allow', frozen=True)

    severity: str | None = None

    @property
    def resolved_severity(self) -> Severity | None:
        return SEVERITY_BY_NAME.get(self.severity) if self.severity else None

    @property
    def options(self) -> dict[str, object]:
        return dict(self.__pydantic_extra__ or {})


RuleEntry = typing.Annotated[bool | str | RuleTable, pydantic.Field(union_mode='left_to_right')]


class SubeditSection(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True, populate_by_name=True)

    # Left unset, the width falls back to the language's own default.
    line_width: int | None = pydantic.Field(default=None, alias='line-width', gt=0)
    exclude: tuple[str, ...] = ()


class ConfigFile(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True)

    subedit: SubeditSection = pydantic.Field(default_factory=SubeditSection)
    rules: dict[str, RuleEntry] = pydantic.Field(default_factory=dict)

    @classmethod
    def parse(cls, raw: typing.Mapping[str, object]) -> 'ConfigFile':
        try:
            return cls.model_validate(raw)
        except pydantic.ValidationError:
            return cls()
