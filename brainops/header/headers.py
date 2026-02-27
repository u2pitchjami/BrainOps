"""
# handlers/header/headers.py
"""

from __future__ import annotations

from datetime import datetime

from brainops.header.get_tags_and_summary import (
    get_summary_from_ollama,
    get_tags_from_ollama,
)
from brainops.models.classification import ClassificationResult
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.metadata import NoteMetadata
from brainops.utils.logger import LoggerProtocol, ensure_logger, with_child_logger


@with_child_logger
def make_properties(
    content: str,
    meta_yaml: NoteMetadata,
    classification: ClassificationResult,
    note_id: int,
    status: str,
    *,
    synthesis_id: int | None = None,  # gardé si tu synchronises ailleurs
    logger: LoggerProtocol | None = None,
) -> NoteMetadata:
    """
    Génère/rafraîchit les propriétés d'une note :

    1) Lecture YAML + body 2) Appels IA (tags + summary) sur le body 3) Mise à jour DB (status, summary, tags,
    word_count) 4) Réécriture YAML consolidée via NoteMetadata

    Retourne True si tout s'est bien passé.
    """
    logger = ensure_logger(logger, __name__)
    try:
        logger.debug("[make_properties] start for (note_id=%s)", note_id)
        logger.debug(f"meta_yaml : {meta_yaml}")
        # 2) Appels IA (sur body uniquement)
        logger.debug("[make_properties] IA: tags + summary")
        tags = get_tags_from_ollama(content, note_id, logger=logger) or []
        summary = (get_summary_from_ollama(content, note_id, logger=logger) or "").strip()

        # 5) Construire l’objet NoteMetadata final (fusion YAML existant + ajouts)
        meta_final = NoteMetadata.merge(
            NoteMetadata(  # priorité aux nouvelles infos
                tags=tags,
                summary=summary,
                status=status,
                category=classification.category_name,
                subcategory=classification.subcategory_name or "",
                last_modified=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                doc_type=meta_yaml.doc_type,
            ),
            meta_yaml,  # puis l’existant
        )

        return meta_final
    except Exception as exc:  # pylint: disable=broad-except
        raise BrainOpsError("construction header KO", code=ErrCode.METADATA, ctx={"note_id": note_id}) from exc
