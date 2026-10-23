import dataclasses


@dataclasses.dataclass(frozen=True, slots=True)
class FileType:
    """A kind of file a parser reads, known by its extensions."""

    language_id: str
    extensions: frozenset[str]
    # The extension Vale and AutoCorrect know the file by, since they read an unknown one as plain text.
    canonical_extension: str
    # Directories a package manager fills with files nobody in the project wrote.
    vendor_directories: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.canonical_extension not in self.extensions:
            raise ValueError(f'{self.canonical_extension} must be one of the extensions of {self.language_id}')

    @property
    def aliases(self) -> dict[str, str]:
        return {
            extension: self.canonical_extension
            for extension in self.extensions
            if extension != self.canonical_extension
        }
