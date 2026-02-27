"""
process_import.utils.large_note.
"""

from __future__ import annotations

import re

from brainops.process_import.split.split_utils import (
    count_tokens,
    split_linear_text,
    split_section_if_needed,
    split_text_safely,
)
from brainops.process_import.split.split_windows_by_paragraphs import split_windows_by_paragraphs
from brainops.utils.logger import LoggerProtocol, ensure_logger


def smart_split_for_embeddings(
    text: str,
    max_tokens: int | None = None,
    max_chars: int = 3800,
    logger: LoggerProtocol | None = None,
) -> list[str]:
    """
    Smart splitting strategy for embeddings.

    Priority:
    1. Structured markdown (titles)
    2. Paragraph-based split
    3. Linear fallback

    :param text: Input text.
    :param max_tokens: Token limit per chunk (preferred).
    :param max_chars: Character fallback limit.
    :param logger: Optional logger.
    :return: List of chunks.
    """
    logger = ensure_logger(logger, __name__)
    text = text.strip()

    if not text:
        logger.debug("Empty text received in smart_split_for_embeddings")
        return []

    title_matches = re.findall(r"(?m)^#{1,5}\s+", text)
    has_paragraphs = "\n\n" in text

    logger.debug(
        "Split decision: titles=%d, paragraphs=%s, max_tokens=%s",
        len(title_matches),
        has_paragraphs,
        max_tokens,
    )

    # --- 1️⃣ Structured markdown (titles)
    if title_matches:
        logger.info("Texte structuré détecté (%d titres)", len(title_matches))

        return split_large_note_by_titles_and_words(
            content=text,
            max_tokens=max_tokens,
            logger=logger,
        )

    # --- 2️⃣ Paragraph-based split
    if has_paragraphs:
        logger.info("Texte non structuré avec paragraphes détecté")

        return split_windows_by_paragraphs(
            text=text,
            max_tokens=max_tokens,
            max_chars=max_chars,
            logger=logger,
        )

    # --- 3️⃣ Linear fallback
    logger.info("Texte non structuré sans paragraphes, split linéaire")

    return split_linear_text(
        text=text,
        max_tokens=max_tokens,
        max_chars=max_chars,
    )


def split_large_note_by_titles_and_words(
    content: str,
    *,
    max_chars: int = 3800,
    max_tokens: int | None = None,
    logger: LoggerProtocol | None = None,
) -> list[str]:
    """
    Découpe un document Markdown structuré par titres (# à #####).

    - Chaque section est garantie <= max_tokens (si fourni)
      sinon <= max_chars
    - Les sections trop longues sont redécoupées intelligemment :
        - paragraphes si possible
        - fallback linéaire sinon
    - Cette fonction NE gère QUE les documents AVEC titres.
    """
    logger = ensure_logger(logger, __name__)
    content = content.strip()

    if not content:
        return []

    title_pattern = r"(?m)^#{1,5}\s+.*$"
    matches = list(re.finditer(title_pattern, content))

    if not matches:
        logger.warning("split_large_note_by_titles_and_words appelée sans titres détectés")
        return split_text_safely(
            text=content,
            max_chars=max_chars,
            max_tokens=max_tokens,
            logger=logger,
        )

    blocks: list[str] = []

    # --- Introduction éventuelle ---
    if matches[0].start() > 0:
        intro = content[: matches[0].start()].strip()
        if intro:
            intro_chunks = split_text_safely(
                text=intro,
                max_chars=max_chars,
                max_tokens=max_tokens,
                logger=logger,
            )
            for chunk in intro_chunks:
                blocks.append(f"## Introduction\n{chunk}".strip())

    # --- Sections Markdown ---
    for i, match in enumerate(matches):
        title = match.group().strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)

        section_content = content[start:end].strip()

        if not section_content:
            blocks.append(title)
            continue

        # 🔎 Taille mesurée selon mode
        if max_tokens is not None:
            size = count_tokens(section_content)
            limit = max_tokens
            unit = "tokens"
        else:
            size = len(section_content)
            limit = max_chars
            unit = "chars"

        logger.debug(
            "Traitement section '%s' (%d %s, limit=%d)",
            title,
            size,
            unit,
            limit,
        )

        section_chunks = split_section_if_needed(
            title=title,
            content=section_content,
            max_chars=max_chars,
            max_tokens=max_tokens,
            logger=logger,
        )

        blocks.extend(section_chunks)

    logger.info(
        "Markdown split terminé : %d blocs (mode=%s)",
        len(blocks),
        "tokens" if max_tokens else "chars",
    )

    return blocks
