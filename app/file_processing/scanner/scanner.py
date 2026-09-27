from pathlib import Path


def scan_folder(folder_path: str) -> list[Path]:
    """Recursively discover and return all files under a folder.

    Raises:
        FileNotFoundError: If the supplied folder path does not exist.
        NotADirectoryError: If the supplied path is not a directory.
    """
    folder = Path(folder_path)

    if not folder.exists():
        raise FileNotFoundError(f"Folder does not exist: {folder_path}")
    if not folder.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {folder_path}")

    return [path for path in folder.rglob("*") if path.is_file()]
