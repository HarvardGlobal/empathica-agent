from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentChunk:
    chunk_index: int
    chunk_text: str
    patient_id: str
    source_path: str
    file_name: str
    document_id: str


def chunk_text(
    text: str,
    *,
    patient_id: str,
    source_path: str,
    file_name: str,
    document_id: str,
    chunk_size_words: int = 800,
    overlap_words: int = 120,
) -> list[DocumentChunk]:
    words = (text or "").split()
    if not words:
        return []

    chunk_size_words = max(1, int(chunk_size_words))
    overlap_words = max(0, min(int(overlap_words), chunk_size_words - 1))
    step = max(1, chunk_size_words - overlap_words)

    chunks: list[DocumentChunk] = []
    start = 0
    chunk_index = 0
    while start < len(words):
        end = min(len(words), start + chunk_size_words)
        chunk_words = words[start:end]
        if chunk_words:
            chunks.append(
                DocumentChunk(
                    chunk_index=chunk_index,
                    chunk_text=" ".join(chunk_words).strip(),
                    patient_id=patient_id,
                    source_path=source_path,
                    file_name=file_name,
                    document_id=document_id,
                )
            )
            chunk_index += 1
        start += step
    return chunks
