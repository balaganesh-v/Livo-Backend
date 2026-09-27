"""Extract filesystem metadata without reading file contents."""

import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FileMetadata:
    name: str
    file_path: str
    extension: str | None
    mime_type: str | None
    size_bytes: int
    file_created_at: datetime
    file_modified_at: datetime
    scanned_at: datetime


def extract_file_metadata(file_path: str | Path) -> FileMetadata:
    """Return basic metadata for a file, raising OSError on access failures."""
    path = Path(file_path)
    stat = path.stat()
    created_timestamp = getattr(stat, "st_birthtime", stat.st_ctime)
    mime_type, _ = mimetypes.guess_type(path.name)
    return FileMetadata(
        name=path.name,
        file_path=str(path.resolve(strict=True)),
        extension=path.suffix.lower() or None,
        mime_type=mime_type,
        size_bytes=stat.st_size,
        file_created_at=datetime.fromtimestamp(created_timestamp, tz=timezone.utc),
        file_modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        scanned_at=datetime.now(timezone.utc),
    )
