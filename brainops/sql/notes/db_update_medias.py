"""
Mise à jour partielle de la table `medias`.
"""

from __future__ import annotations

import json
from typing import Any

from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.sql.db_connection import get_db_connection
from brainops.utils.logger import (
    LoggerProtocol,
    ensure_logger,
    with_child_logger,
)

_ALLOWED_COLUMNS_MEDIAS: set[str] = {
    "media_type",
    "doc_type",
    "provider",
    "source_url",
    "storage_path",
    "language",
    "published_at",
    "duration_seconds",
    "file_size_bytes",
    "checksum",
    "manifest_version",
    "editorial_context",
}


def _prepare_media_update_value(column: str, value: Any) -> Any:
    """
    Prépare une valeur avant sa transmission au driver MariaDB.
    """

    if column == "analysis_instructions":
        if value is None:
            return None

        if not isinstance(value, list):
            raise ValueError("'analysis_instructions' doit être une liste de chaînes.")

        instructions: list[str] = []

        for index, instruction in enumerate(value):
            if not isinstance(instruction, str):
                raise ValueError(f"'analysis_instructions' contient une valeur invalide à l'index {index}.")

            cleaned_instruction = instruction.strip()
            if cleaned_instruction:
                instructions.append(cleaned_instruction)

        return json.dumps(
            instructions,
            ensure_ascii=False,
        )

    return value


@with_child_logger
def update_obsidian_medias(
    media_id: int,
    updates: dict[str, Any],
    *,
    logger: LoggerProtocol | None = None,
) -> bool:
    """
    Met à jour certains champs autorisés d'un média existant.

    Retourne `True` lorsqu'une requête de mise à jour a été exécutée,
    sinon `False`.
    """
    logger = ensure_logger(logger, __name__)

    if media_id <= 0:
        raise ValueError("media_id doit être un entier strictement positif.")

    if not updates:
        logger.debug(
            "[MEDIA] Aucun champ à mettre à jour (id=%s)",
            media_id,
        )
        return False

    filtered = {key: value for key, value in updates.items() if key in _ALLOWED_COLUMNS_MEDIAS}

    rejected_columns = sorted(set(updates) - _ALLOWED_COLUMNS_MEDIAS)

    if rejected_columns:
        logger.warning(
            "[MEDIA] Colonnes ignorées car non autorisées : %s",
            rejected_columns,
        )

    if not filtered:
        logger.warning(
            "[MEDIA] Aucun champ autorisé dans updates (id=%s)",
            media_id,
        )
        return False

    try:
        prepared_updates = {column: _prepare_media_update_value(column, value) for column, value in filtered.items()}
    except (TypeError, ValueError) as exc:
        raise BrainOpsError(
            "Valeurs invalides pour la mise à jour du média",
            code=ErrCode.DB,
            ctx={
                "media_id": media_id,
                "columns": list(filtered),
            },
        ) from exc

    set_clause = ", ".join(f"{column} = %s" for column in prepared_updates)

    values = [
        *prepared_updates.values(),
        media_id,
    ]

    conn = get_db_connection(logger=logger)

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE medias SET {set_clause} WHERE id = %s",
                values,
            )

            affected_rows = cur.rowcount
            conn.commit()

    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            logger.exception(
                "[MEDIA] Échec du rollback (id=%s)",
                media_id,
            )

        raise BrainOpsError(
            "Mise à jour MEDIA en base impossible",
            code=ErrCode.DB,
            ctx={
                "media_id": media_id,
                "columns": list(prepared_updates),
            },
        ) from exc

    finally:
        conn.close()

    if affected_rows == 0:
        logger.warning(
            "[MEDIA] Aucun média modifié pour id=%s",
            media_id,
        )
        return False

    logger.info(
        "[MEDIA] Mise à jour OK (id=%s) : %s",
        media_id,
        list(prepared_updates),
    )

    return True
