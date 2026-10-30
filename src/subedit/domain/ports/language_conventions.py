import abc
import dataclasses

from ..models.comment import CommentForm, Visibility


@dataclasses.dataclass(frozen=True, slots=True)
class DelimiterSplit:
    """A comment line split into its indent, its delimiter, its text, and what closes it."""

    indent: str
    delimiter: str
    text: str
    suffix: str = ''


class LanguageConventions(abc.ABC):
    """How a language writes its comments, which the rules ask about without knowing its grammar."""

    language_id: str
    extensions: frozenset[str]
    # A format with no doc comment, such as YAML, has no delimiter to name and no tags that restate a signature.
    doc_delimiter: str | None = None
    signature_tags: tuple[str, ...] = ()

    @abc.abstractmethod
    def visibility_of(self, name: str) -> Visibility: ...

    @abc.abstractmethod
    def split_delimiter(self, line: str, form: CommentForm) -> DelimiterSplit: ...
