import pathlib
import typing


def as_known_path(path: str, suffix_aliases: typing.Mapping[str, str]) -> str:
    """The path with its extension swapped for the one a prose tool knows, such as .ts for a .mts module.

    A tool reads a file type it does not know as plain text, code and all.
    """
    source_path = pathlib.Path(path)
    suffix = suffix_aliases.get(source_path.suffix)
    return str(source_path.with_suffix(suffix)) if suffix else path
