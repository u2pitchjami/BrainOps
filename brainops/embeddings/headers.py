"""
# handlers/header/headers.py
"""

from __future__ import annotations

from datetime import datetime

from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.metadata import NoteMetadata
from brainops.utils.logger import LoggerProtocol, ensure_logger


def make_properties(
    meta_yaml: NoteMetadata,
    tags: list[str],
    summary: str | None,
    status: str,
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
        logger.debug(f"meta_yaml : {meta_yaml}")
        logger.debug(f"analysis_profile : {meta_yaml.analysis_profile}")
        # 2) Appels IA (sur body uniquement)

        # 5) Construire l’objet NoteMetadata final (fusion YAML existant + ajouts)
        meta_final = NoteMetadata.merge(
            NoteMetadata(  # priorité aux nouvelles infos
                status=status,
                tags=tags,
                summary=summary if summary else "",
                last_modified=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                doc_type=meta_yaml.doc_type,
                analysis_profile=meta_yaml.analysis_profile,
            ),
            meta_yaml,  # puis lexistant
        )

        return meta_final
    except Exception as exc:  # pylint: disable=broad-except
        raise BrainOpsError(
            "construction header KO",
            code=ErrCode.METADATA,
        ) from exc
