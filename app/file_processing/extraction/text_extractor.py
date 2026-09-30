"""Bounded, best-effort extraction of common text files."""

from pathlib import Path

MAX_TEXT_EXTRACTION_BYTES = 5 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024


def extract_text_file(
    file_path: str | Path,
    max_bytes: int = MAX_TEXT_EXTRACTION_BYTES,
) -> dict[str, object]:
    """Read at most ``max_bytes`` and decode text with replacement on errors."""
    if max_bytes < 0:
        raise ValueError("max_bytes must be non-negative")

    path = Path(file_path)
    chunks: list[bytes] = []
    remaining = max_bytes
    with path.open("rb") as stream:
        while remaining:
            chunk = stream.read(min(READ_CHUNK_BYTES, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        truncated = bool(stream.read(1))

    content = b"".join(chunks).decode("utf-8", errors="replace")
    return {
        "success": True,
        "content": content,
        "content_length": len(content),
        "truncated": truncated,
        "error": None,
    }
