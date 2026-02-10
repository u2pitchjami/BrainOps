"""
process_import.utils.large_note.
"""

from __future__ import annotations

from collections.abc import Sequence
import re

from brainops.utils.logger import LoggerProtocol, ensure_logger


def split_large_note(content: str, max_words: int = 1000) -> list[str]:
    """
    Découpe une note en blocs de taille optimale (max_words).
    """
    words = content.split()
    blocks: list[str] = []
    current_block: list[str] = []

    for word in words:
        current_block.append(word)
        if len(current_block) >= max_words:
            blocks.append(" ".join(current_block))
            current_block = []

    if current_block:
        blocks.append(" ".join(current_block))
    return blocks


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


def split_text_safely(text: str, max_chars: int = 3800, logger: LoggerProtocol | None = None) -> list[str]:
    """
    Découpe robuste :

    1. paragraphes (si présents)
    2. fallback linéaire par caractères
    """
    logger = ensure_logger(logger, __name__)
    logger.warning("split_text_safely activé (texte de %d chars)", len(text))
    text = text.strip()
    if not text:
        return []

    if len(text) <= max_chars:
        logger.debug("Texte OK, pas de split nécessaire")
        return [text]

    paragraphs = [p for p in re.split(r"\n{2,}", text) if p.strip()]
    if len(paragraphs) > 1:
        logger.debug("Texte structuré en %d paragraphes, split par paragraphes", len(paragraphs))
        chunks: list[str] = []
        buf = ""

        for p in paragraphs:
            if not buf:
                buf = p
                continue

            if len(buf) + 2 + len(p) <= max_chars:
                buf = f"{buf}\n\n{p}"
            else:
                chunks.append(buf)
                buf = p

        if buf:
            chunks.append(buf)

        return chunks

    # 🔴 fallback ultime (transcription audio)
    logger.warning("Fallback split linéaire (aucun paragraphe détecté)")
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def split_section_if_needed(
    title: str, content: str, max_chars: int = 3800, logger: LoggerProtocol | None = None
) -> list[str]:
    """
    Garantit qu'une section Markdown respecte la limite caractères.
    """
    logger = ensure_logger(logger, __name__)
    logger.debug("Vérification section '%s' (%d chars)", title.strip(), len(content.strip()))
    header = title.strip()
    body = content.strip()
    full = f"{header}\n{body}"

    if len(full) <= max_chars:
        logger.debug("Section '%s' OK (%d chars)", header, len(full))
        return [full]

    logger.info("Section trop longue, découpage activé: %s", header)
    sub_chunks = split_text_safely(body, max_chars=max_chars)

    return [f"{header}\n{chunk}".strip() for chunk in sub_chunks]


def split_linear_text(
    text: str,
    max_chars: int = 3800,
    overlap: int = 350,
) -> list[str]:
    """
    Fallback ultime pour texte sans paragraphes (ex: transcription audio).
    """
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + max_chars, length)
        chunk = text[start:end]

        if chunks:
            chunk = text[max(0, start - overlap) : end]

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
