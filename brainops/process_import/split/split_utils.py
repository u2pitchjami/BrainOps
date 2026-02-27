"""
process_import.utils.large_note.
"""

from __future__ import annotations

from collections.abc import Sequence
import re

import tiktoken

from brainops.utils.logger import LoggerProtocol, ensure_logger

_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """
    Count tokens using cl100k_base encoding.
    """
    return len(_ENCODING.encode(text))


def split_large_note(
    content: str,
    *,
    max_chars: int = 3800,
    max_tokens: int | None = None,
) -> list[str]:
    """
    Découpe un texte non structuré en blocs linéaires.

    Priority:
    - max_tokens if provided
    - else max_chars

    :param content: Input text.
    :param max_chars: Maximum characters per chunk (default mode).
    :param max_tokens: Optional token limit.
    :return: List of chunks.
    """
    content = content.strip()
    if not content:
        return []

    # --- Mode selection ---
    if max_tokens is not None:
        mode = "tokens"
        limit = max_tokens
    else:
        mode = "chars"
        limit = max_chars

    chunks: list[str] = []

    if mode == "tokens":
        words = content.split()
        buffer: list[str] = []
        current_tokens = 0

        for word in words:
            word_tokens = count_tokens(word)

            if current_tokens + word_tokens <= limit:
                buffer.append(word)
                current_tokens += word_tokens
            else:
                chunks.append(" ".join(buffer))
                buffer = [word]
                current_tokens = word_tokens

        if buffer:
            chunks.append(" ".join(buffer))

        return chunks

    # --- Char mode (plus simple et plus cohérent)
    start = 0
    length = len(content)

    while start < length:
        end = min(start + limit, length)
        chunk = content[start:end]
        chunks.append(chunk.strip())
        start += limit

    return chunks


def split_large_note_by_titles(content: str) -> list[str]:
    """
    Découpe en blocs basés sur les titres (#, ##, ###), gère l'intro avant le 1er titre.

    Chaque bloc contient le titre et son contenu.
    """
    title_pattern = r"(?m)^(\#{1,3})\s+.*$"
    matches = list(re.finditer(title_pattern, content))

    blocks: list[str] = []
    if matches:
        if matches[0].start() > 0:
            intro = content[: matches[0].start()].strip()
            if intro:
                blocks.append("## **Introduction**\n\n" + intro)

        for i, match in enumerate(matches):
            title = match.group().strip()
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            section_content = content[start_pos:end_pos].strip()
            blocks.append(f"{title}\n{section_content}")
    else:
        intro = content.strip()
        if intro:
            blocks.append("## **Introduction**\n\n" + intro)

    return blocks


def split_text_safely(
    text: str,
    max_chars: int = 3800,
    max_tokens: int | None = None,
    logger: LoggerProtocol | None = None,
) -> list[str]:
    """
    Découpe robuste :

    - paragraphes
    - fallback linéaire
    Support tokens optionnel.
    """
    logger = ensure_logger(logger, __name__)
    text = text.strip()

    if not text:
        return []

    if max_tokens is not None:
        if count_tokens(text) <= max_tokens:
            return [text]
    else:
        if len(text) <= max_chars:
            return [text]

    paragraphs = [p for p in re.split(r"\n{2,}", text) if p.strip()]

    if len(paragraphs) > 1:
        chunks: list[str] = []
        buffer: list[str] = []
        current_size = 0

        for p in paragraphs:
            size = count_tokens(p) if max_tokens else len(p)

            limit = max_tokens if max_tokens else max_chars

            if current_size + size <= limit:
                buffer.append(p)
                current_size += size
            else:
                chunks.append("\n\n".join(buffer))
                buffer = [p]
                current_size = size

        if buffer:
            chunks.append("\n\n".join(buffer))

        return chunks

    # fallback ultime
    if max_tokens is not None:
        return split_linear_text(text, max_tokens=max_tokens)

    return split_linear_text(text, max_chars=max_chars)


def split_section_if_needed(
    title: str,
    content: str,
    max_chars: int = 3800,
    max_tokens: int | None = None,
    logger: LoggerProtocol | None = None,
) -> list[str]:
    logger = ensure_logger(logger, __name__)

    header = title.strip()
    body = content.strip()
    full = f"{header}\n{body}"

    size = count_tokens(full) if max_tokens else len(full)
    limit = max_tokens if max_tokens else max_chars

    if size <= limit:
        return [full]

    sub_chunks = split_text_safely(
        body,
        max_chars=max_chars,
        max_tokens=max_tokens,
        logger=logger,
    )

    return [f"{header}\n{chunk}".strip() for chunk in sub_chunks]


def split_linear_text(
    text: str,
    max_chars: int = 3800,
    max_tokens: int | None = None,
    overlap: int = 350,
) -> list[str]:
    """
    Fallback ultime.
    """
    text = text.strip()
    if not text:
        return []

    if max_tokens is not None:
        words = text.split()
        chunks: list[str] = []
        buffer: list[str] = []
        current_tokens = 0

        for word in words:
            word_tokens = count_tokens(word)

            if current_tokens + word_tokens <= max_tokens:
                buffer.append(word)
                current_tokens += word_tokens
            else:
                chunks.append(" ".join(buffer))
                buffer = [word]
                current_tokens = word_tokens

        if buffer:
            chunks.append(" ".join(buffer))

        return chunks

    # fallback historique char
    chunks = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + max_chars, length)
        chunk = text[start:end]
        chunks.append(chunk.strip())
        start += max_chars - overlap

    return chunks


def ensure_titles_in_blocks(blocks: Sequence[str], default_title: str = "# Introduction") -> list[str]:
    """
    S'assure que chaque bloc commence par un titre Markdown ; sinon en ajoute un.
    """
    processed: list[str] = []
    for i, block in enumerate(blocks):
        b = (block or "").strip()
        if not b.startswith("#"):
            title = default_title if i == 0 else f"# Section {i + 1}"
            b = f"{title}\n{b}"
        processed.append(b)
    return processed
