import json
from pathlib import Path
from typing import Any


def _clean_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def _chunk_text(text: str, max_chars: int = 1800, overlap: int = 200) -> list[str]:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            split_at = text.rfind(". ", start, end)
            if split_at > start + max_chars // 2:
                end = split_at + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def _walk_json(
    node: Any,
    source_file: str,
    category: str,
    path: str = "root",
) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []

    if isinstance(node, dict):
        scalar_lines: list[str] = []
        child_items: list[tuple[str, Any]] = []

        for key, value in node.items():
            child_path = f"{path}.{key}"
            if isinstance(value, (dict, list)):
                child_items.append((child_path, value))
            else:
                scalar = _clean_scalar(value)
                if scalar:
                    scalar_lines.append(f"{key}: {scalar}")

        if scalar_lines:
            prefix = f"Category: {category}\nJSON path: {path}\n"
            text = prefix + "\n".join(scalar_lines)
            for index, chunk in enumerate(_chunk_text(text)):
                documents.append(
                    {
                        "id": f"{source_file}:{path}:{index}",
                        "text": chunk,
                        "metadata": {
                            "source_file": source_file,
                            "category": category,
                            "path": path,
                        },
                    }
                )

        for child_path, child in child_items:
            documents.extend(_walk_json(child, source_file, category, child_path))

    elif isinstance(node, list):
        for index, item in enumerate(node):
            documents.extend(
                _walk_json(
                    item,
                    source_file=source_file,
                    category=category,
                    path=f"{path}[{index}]",
                )
            )
    else:
        scalar = _clean_scalar(node)
        if scalar:
            documents.append(
                {
                    "id": f"{source_file}:{path}:0",
                    "text": f"Category: {category}\nJSON path: {path}\nvalue: {scalar}",
                    "metadata": {
                        "source_file": source_file,
                        "category": category,
                        "path": path,
                    },
                }
            )

    return documents


def load_json_documents(data_dir: Path) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []

    for file_path in sorted(data_dir.rglob("*.json")):
        relative_path = file_path.relative_to(data_dir).as_posix()
        category = relative_path.split("/", 1)[0]

        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"[SKIP] {relative_path}: {exc}")
            continue

        documents.extend(
            _walk_json(
                payload,
                source_file=relative_path,
                category=category,
            )
        )

    return documents
