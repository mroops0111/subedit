import dataclasses
import pathlib


@dataclasses.dataclass(frozen=True, slots=True)
class FileType:
    """A kind of file a parser reads, known by its extensions or, for a file git names, by its whole name."""

    language_id: str
    extensions: frozenset[str]
    # The extension Vale and AutoCorrect know the file by, since they read an unknown one as plain text.
    canonical_extension: str
    # The kind of prose the file holds, which a project's config names to set rules for it alone.
    surface: str
    # Directories a package manager fills with files nobody in the project wrote.
    vendor_directories: frozenset[str] = frozenset()
    # Files a tool writes whole, such as a lock file, which no one reads as prose.
    generated_names: frozenset[str] = frozenset()
    # Names that mark the file whatever its extension, such as COMMIT_EDITMSG, which has none.
    file_names: frozenset[str] = frozenset()
    # The width the file's own convention sets, such as git's 72 for a commit message,
    # which a project's line-width for its code does not reach.
    line_width: int | None = None

    def __post_init__(self) -> None:
        if self.canonical_extension not in self.extensions and not self.file_names:
            raise ValueError(f'{self.canonical_extension} must be one of the extensions of {self.language_id}')

    @property
    def aliases(self) -> dict[str, str]:
        """The extension a prose tool knows each other extension and each file name by."""
        return {
            **dict.fromkeys(self.file_names, self.canonical_extension),
            **{
                extension: self.canonical_extension
                for extension in self.extensions
                if extension != self.canonical_extension
            },
        }

    def matches(self, path: pathlib.PurePath) -> bool:
        return path.name in self.file_names or path.suffix in self.extensions
