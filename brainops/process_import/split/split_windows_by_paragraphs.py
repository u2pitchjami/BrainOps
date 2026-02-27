"""
# process/split_windows_by_paragraphs.py
"""

from __future__ import annotations

import re

from brainops.process_import.split.split_utils import count_tokens
from brainops.utils.logger import LoggerProtocol, ensure_logger


def split_windows_by_paragraphs(
    text: str,
    *,
    max_chars: int = 3800,
    max_tokens: int | None = None,
    logger: LoggerProtocol | None = None,
) -> list[str]:
    """
    Split text by logical paragraphs and group them under size limit.

    Priority:
    - max_tokens if provided
    - else max_chars

    :param text: Input text.
    :param max_chars: Maximum characters per chunk (default mode).
    :param max_tokens: Optional token limit (preferred if set).
    :param logger: Optional logger.
    :return: List of chunks.
    """
    logger = ensure_logger(logger, __name__)
    text = text.strip()

    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    logger.debug("Detected %d paragraphs", len(paragraphs))

    # --- Mode selection ---
    if max_tokens is not None:
        mode = "tokens"
        limit = max_tokens
    else:
        mode = "chars"
        limit = max_chars

    logger.debug("Paragraph grouping mode=%s limit=%d", mode, limit)

    chunks: list[str] = []
    buffer: list[str] = []
    current_size = 0

    for paragraph in paragraphs:
        if mode == "tokens":
            size = count_tokens(paragraph)
        else:
            size = len(paragraph)

        if size > limit:
            logger.warning(
                "Single paragraph exceeds %s limit (%d > %d)",
                mode,
                size,
                limit,
            )
            chunks.append(paragraph)
            continue

        if current_size + size <= limit:
            buffer.append(paragraph)
            current_size += size
        else:
            chunks.append("\n\n".join(buffer))
            buffer = [paragraph]
            current_size = size

    if buffer:
        chunks.append("\n\n".join(buffer))

    logger.info(
        "Paragraph grouping complete: %d chunks (mode=%s, limit=%d)",
        len(chunks),
        mode,
        limit,
    )

    return chunks
