from __future__ import annotations


def chunk_text(text: str, max_chars: int = 1800, overlap: int = 200) -> list[str]:
    """Split normalized PostgreSQL row text into deterministic overlapping chunks."""
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [normalized]

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + max_chars, len(normalized))
        if end < len(normalized):
            split_at = normalized.rfind(". ", start, end)
            if split_at > start + max_chars // 2:
                end = split_at + 1
        chunks.append(normalized[start:end].strip())
        if end >= len(normalized):
            break
        start = max(0, end - overlap)
    return chunks
