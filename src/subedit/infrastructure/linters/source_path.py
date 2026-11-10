import pathlib
import typing


def as_known_path(path: str, aliases: typing.Mapping[str, str]) -> str:
    """The path with its extension swapped for the one a prose tool knows, such as .ts for a .mts module.

    A file known by its name, such as COMMIT_EDITMSG, takes the extension after its name.
    A tool reads a file type it does not know as plain text, code and all.
    """
    source_path = pathlib.Path(path)
    named = aliases.get(source_path.name)
    if named is not None:
        return str(source_path.with_name(source_path.name + named))
    suffix = aliases.get(source_path.suffix)
    return str(source_path.with_suffix(suffix)) if suffix else path
