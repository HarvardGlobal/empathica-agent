from __future__ import annotations

import re


def normalize_whitespace(text: str) -> str:
    """Collapse all whitespace sequences to a single space and strip leading/trailing."""
    return re.sub(r"\s+", " ", text).strip()


def estimate_token_count(text: str) -> int:
    """Estimate token count: word count * 1.3."""
    word_count = len(text.split())
    return int(word_count * 1.3)


def chunk_label_section(section_text: str, section_type: str) -> list[str]:  # noqa: ARG001
    """
    Split a label section into chunks targeting 300-800 words.

    Strategy:
    1. Split on double newlines (paragraphs).
    2. Merge small paragraphs together until we approach the target size.
    3. Split over-large paragraphs at sentence boundaries.

    Returns a list of clean, whitespace-normalized chunk strings.
    """
    TARGET_MIN_WORDS = 300
    TARGET_MAX_WORDS = 800

    if not section_text or not section_text.strip():
        return []

    # Step 1: split into paragraphs on double newlines
    raw_paragraphs = re.split(r"\n{2,}", section_text)
    paragraphs: list[str] = []
    for p in raw_paragraphs:
        cleaned = normalize_whitespace(p)
        if cleaned:
            paragraphs.append(cleaned)

    if not paragraphs:
        return []

    # Step 2: split paragraphs that exceed TARGET_MAX_WORDS into sentences
    def split_paragraph_to_sentences(para: str) -> list[str]:
        sentences = re.split(r"(?<=[.!?])\s+", para)
        chunks: list[str] = []
        current_words: list[str] = []
        for sentence in sentences:
            sentence_words = sentence.split()
            if len(current_words) + len(sentence_words) > TARGET_MAX_WORDS and current_words:
                chunks.append(" ".join(current_words))
                current_words = sentence_words
            else:
                current_words.extend(sentence_words)
        if current_words:
            chunks.append(" ".join(current_words))
        return chunks

    split_paras: list[str] = []
    for para in paragraphs:
        if len(para.split()) > TARGET_MAX_WORDS:
            split_paras.extend(split_paragraph_to_sentences(para))
        else:
            split_paras.append(para)

    # Step 3: merge small chunks together until they reach TARGET_MIN_WORDS
    final_chunks: list[str] = []
    buffer_words: list[str] = []

    for para in split_paras:
        para_words = para.split()
        if len(buffer_words) + len(para_words) <= TARGET_MAX_WORDS:
            buffer_words.extend(para_words)
        else:
            if buffer_words:
                final_chunks.append(" ".join(buffer_words))
            buffer_words = para_words

    if buffer_words:
        final_chunks.append(" ".join(buffer_words))

    # Filter empty strings just in case
    return [c for c in final_chunks if c.strip()]
