"""Bounded UTF-8 text extraction."""

from pathlib import Path

MAX_TEXT_EXTRACTION_BYTES = 5 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024


def extract_text(file_path: str | Path) -> tuple[str, bool]:
    """Read at most the configured byte limit, replacing invalid UTF-8 bytes."""
    path = Path(file_path)
    chunks: list[bytes] = []
    remaining = MAX_TEXT_EXTRACTION_BYTES
    with path.open("rb") as stream:
        while remaining:
            chunk = stream.read(min(READ_CHUNK_BYTES, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)

        # Reading one extra byte distinguishes an exact-limit file from a truncated one.
        truncated = bool(remaining == 0 and stream.read(1))

    content = b"".join(chunks).decode("utf-8-sig", errors="replace")
    return content, truncated
