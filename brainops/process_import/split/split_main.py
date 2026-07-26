"""
process_import.utils.large_note.
"""

from __future__ import annotations

from collections.abc import Sequence
import re
from typing import Literal

from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.process_import.split.split_qa_paragraphs import split_qa_paragraphs
from brainops.process_import.split.split_utils import (
    count_tokens,
    split_large_note,
    split_large_note_by_titles,
    split_linear_text,
    split_section_if_needed,
    split_text_safely,
)
from brainops.process_import.split.split_windows_by_paragraphs import split_windows_by_paragraphs
from brainops.utils.logger import LoggerProtocol, ensure_logger

type SplitMethod = Literal[
    "auto",
    "titles_and_words",
    "titles",
    "words",
    "qa_paragraphs",
    "split_windows_by_paragraphs",
]


def split_note_content(
    *,
    content: str,
    split_method: SplitMethod,
    max_tokens: int,
    max_chars: int,
    logger: LoggerProtocol,
    note_id: int | None = None,
) -> list[str]:
    """
    Découpe le contenu d'une note selon la stratégie demandée.

    Cette fonction sélectionne uniquement la stratégie de découpage.
    Elle ne gère ni les appels IA, ni la persistance, ni l'écriture
    des résultats.

    Args:
        content: Contenu textuel à découper.
        split_method: Stratégie de découpage à appliquer.
        max_tokens: Nombre maximal de tokens par bloc.
        max_chars: Nombre maximal de caractères par bloc.
        logger: Logger BrainOps.
        note_id: Identifiant facultatif de la note, utilisé pour les logs
            et le contexte des erreurs.

    Returns:
        La liste des blocs textuels non vides.

    Raises:
        ValueError: Si le contenu ou les limites sont invalides.
        BrainOpsError: Si la méthode de découpage est inconnue ou si aucun
            bloc exploitable n'est produit.
    """
    normalized_content = content.strip()

    if not normalized_content:
        raise ValueError("Le contenu à découper ne peut pas être vide")

    if max_tokens <= 0:
        raise ValueError(f"max_tokens doit être strictement positif : {max_tokens}")

    if max_chars <= 0:
        raise ValueError(f"max_chars doit être strictement positif : {max_chars}")

    logger.debug(
        ("Début du découpage de la note : note_id=%s, méthode=%s, caractères=%d, max_tokens=%d, max_chars=%d"),
        note_id,
        split_method,
        len(normalized_content),
        max_tokens,
        max_chars,
    )

    match split_method:
        case "auto":
            raw_blocks = smart_split_for_embeddings(
                normalized_content,
                max_tokens,
                max_chars,
                logger,
            )

        case "titles_and_words":
            raw_blocks = split_large_note_by_titles_and_words(
                content=normalized_content,
                max_tokens=max_tokens,
                max_chars=max_chars,
                logger=logger,
            )

        case "titles":
            raw_blocks = split_large_note_by_titles(
                normalized_content,
            )

        case "words":
            raw_blocks = split_large_note(
                content=normalized_content,
                max_tokens=max_tokens,
                max_chars=max_chars,
            )

        case "qa_paragraphs":
            raw_blocks = split_qa_paragraphs(
                text=normalized_content,
                logger=logger,
            )

        case "split_windows_by_paragraphs":
            raw_blocks = split_windows_by_paragraphs(
                text=normalized_content,
                max_tokens=max_tokens,
                max_chars=max_chars,
                logger=logger,
            )

        case _:
            logger.error(
                "Méthode de découpage inconnue : note_id=%s, méthode=%s",
                note_id,
                split_method,
            )

            raise BrainOpsError(
                f"Méthode de découpage inconnue : {split_method}",
                code=ErrCode.UNEXPECTED,
                ctx={
                    "note_id": note_id,
                    "split_method": split_method,
                },
            )

    blocks = _normalize_split_blocks(raw_blocks)

    if not blocks:
        logger.error(
            ("Le découpage n'a produit aucun bloc exploitable : note_id=%s, méthode=%s"),
            note_id,
            split_method,
        )

        raise BrainOpsError(
            "Le découpage de la note n'a produit aucun bloc exploitable",
            code=ErrCode.UNEXPECTED,
            ctx={
                "note_id": note_id,
                "split_method": split_method,
            },
        )

    logger.info(
        ("Note découpée : note_id=%s, blocs=%d, méthode=%s"),
        note_id,
        len(blocks),
        split_method,
    )

    return blocks


def _normalize_split_blocks(
    blocks: Sequence[str],
) -> list[str]:
    """
    Nettoie les blocs produits par une stratégie de découpage.

    Args:
        blocks: Blocs textuels bruts.

    Returns:
        Les blocs nettoyés, sans éléments vides.
    """
    normalized_blocks: list[str] = []

    for block in blocks:
        normalized_block = block.strip()

        if normalized_block:
            normalized_blocks.append(normalized_block)

    return normalized_blocks


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
