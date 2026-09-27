"""Safe recursive file discovery."""

import os
from pathlib import Path


def _raise_walk_error(error: OSError) -> None:
    raise error


def scan_folder(folder_path: str | Path) -> list[Path]:
    """Return regular files beneath a directory without following symlinks."""
    folder = Path(folder_path).expanduser()
    try:
        if not folder.exists():
            raise FileNotFoundError("Selected folder does not exist")
        if not folder.is_dir():
            raise NotADirectoryError("Selected path is not a directory")

        discovered: list[Path] = []
        for current, directories, filenames in os.walk(
            folder,
            followlinks=False,
            onerror=_raise_walk_error,
        ):
            directories[:] = [
                name
                for name in directories
                if not (Path(current) / name).is_symlink()
            ]
            for filename in filenames:
                path = Path(current) / filename
                if not path.is_symlink() and path.is_file():
                    discovered.append(path)
        return discovered
    except PermissionError:
        raise


__all__ = ["scan_folder"]
