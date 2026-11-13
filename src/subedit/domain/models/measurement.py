import dataclasses

from .rule_option import CountOption


@dataclasses.dataclass(frozen=True, slots=True)
class Measurement:
    """One value a project's prose holds for a rule's count option, measured as the rule reads it."""

    option: CountOption
    value: int
