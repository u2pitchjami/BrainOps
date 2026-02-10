"""
process_import.utils.large_note.
"""

from __future__ import annotations

import re

from brainops.process_import.split.split_utils import split_linear_text, split_section_if_needed, split_text_safely
from brainops.process_import.split.split_windows_by_paragraphs import split_windows_by_paragraphs
from brainops.utils.logger import LoggerProtocol, ensure_logger


def smart_split_for_embeddings(text: str, logger: LoggerProtocol | None = None) -> list[str]:
    logger = ensure_logger(logger, __name__)
    if re.search(r"(?m)^#{1,5}\s+", text):
        logger.info("Texte structuré détecté, split par titres et mots")
        return split_large_note_by_titles_and_words(text, logger=logger)

    if "\n\n" in text:
        logger.info("Texte non structuré avec paragraphes détecté, split par paragraphes")
        return split_windows_by_paragraphs(text, logger=logger)

    logger.info("Texte non structuré sans paragraphes, split linéaire")
    return split_linear_text(text)


def split_large_note_by_titles_and_words(
    content: str, *, max_chars: int = 3800, logger: LoggerProtocol | None = None
) -> list[str]:
    """
    Découpe un document Markdown structuré par titres (# à #####).

    - Chaque section est garantie <= max_chars
    - Les sections trop longues sont redécoupées intelligemment :
        - paragraphes si possible
        - fallback linéaire sinon
    - Cette fonction NE gère QUE les documents AVEC titres.
      (le fallback global est géré ailleurs)
    """
    logger = ensure_logger(logger, __name__)
    content = content.strip()
    if not content:
        return []

    title_pattern = r"(?m)^#{1,5}\s+.*$"
    matches = list(re.finditer(title_pattern, content))

    if not matches:
        logger.warning("split_large_note_by_titles_and_words appelée sans titres détectés")
        # Sécurité : on ne laisse jamais passer un bloc géant
        return split_text_safely(content, max_chars=max_chars)

    blocks: list[str] = []

    # --- Introduction éventuelle avant le premier titre ---
    if matches[0].start() > 0:
        intro = content[: matches[0].start()].strip()
        if intro:
            intro_chunks = split_text_safely(intro, max_chars=max_chars)
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

        logger.debug(
            "Traitement section '%s' (%d chars)",
            title,
            len(section_content),
        )
        section_chunks = split_section_if_needed(
            title=title,
            content=section_content,
            max_chars=max_chars,
        )
        blocks.extend(section_chunks)

    return blocks
