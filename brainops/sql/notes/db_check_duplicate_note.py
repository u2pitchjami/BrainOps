"""
# sql/db_notes_utils.py
"""

from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Any

from brainops.header.header_utils import hash_source
from brainops.models.note_context import NoteContext
from brainops.sql.db_connection import get_db_connection, get_dict_cursor
from brainops.sql.db_utils import safe_execute_dict
from brainops.utils.files import hash_file_content
from brainops.utils.logger import LoggerProtocol, ensure_logger


def check_duplicate(
    ctx: NoteContext,
    threshold: float = 0.9,
    *,
    logger: LoggerProtocol | None = None,
) -> tuple[bool, list[dict[str, Any]]]:
    """
    Cherche des doublons côté 'archive' via:

    - fuzzy match sur le titre,
    - source_hash,
    - content_hash.
    """
    logger = ensure_logger(logger, __name__)
    source_hash = None
    try:
        if ctx.note_metadata:
            source_hash = hash_source(ctx.note_metadata.source)
        content_hash = hash_file_content(ctx.file_path)

        conn = get_db_connection(logger=logger)

        matches: list[dict[str, Any]] = []
        seen_ids: set[int] = set()
        try:
            with get_dict_cursor(conn) as cur:
                # fuzzy titre
                title_cleaned = clean_title(ctx.note_db.title or "")
                rows = safe_execute_dict(
                    cur,
                    "SELECT id, title FROM obsidian_notes WHERE status=%s",
                    ("archive",),
                    logger=logger,
                ).fetchall()
                for existing_id, existing_title in rows:
                    similarity = SequenceMatcher(None, title_cleaned, existing_title or "").ratio()
                    if similarity >= threshold and existing_id not in seen_ids:
                        matches.append(
                            {
                                "id": int(existing_id),
                                "title": existing_title,
                                "similarity": round(similarity, 3),
                                "match_type": "title",
                            }
                        )
                        seen_ids.add(int(existing_id))

                # source_hash exact
                if source_hash:
                    for row in safe_execute_dict(
                        cur,
                        "SELECT id, title FROM obsidian_notes WHERE status=%s AND source_hash=%s",
                        ("archive", source_hash),
                        logger=logger,
                    ).fetchall():
                        if int(row["id"]) not in seen_ids:
                            matches.append(
                                {
                                    "id": int(row["id"]),
                                    "title": row["title"],
                                    "similarity": 1.0,
                                    "match_type": "source_hash",
                                }
                            )
                            seen_ids.add(int(row["id"]))

                # content_hash exact
                for row in safe_execute_dict(
                    cur,
                    "SELECT id, title FROM obsidian_notes WHERE status=%s AND content_hash=%s",
                    ("archive", content_hash),
                    logger=logger,
                ).fetchall():
                    if int(row["id"]) not in seen_ids:
                        matches.append(
                            {
                                "id": int(row["id"]),
                                "title": row["title"],
                                "similarity": 1.0,
                                "match_type": "content_hash",
                            }
                        )
                        seen_ids.add(int(row["id"]))
        finally:
            conn.close()

        if matches:
            logger.info("[DUP] %s doublon(s) détecté(s) pour note_id=%s", len(matches), ctx.note_db.id)
            logger.debug("[DUP] matches =%s", matches)
            return True, matches
        return False, []
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("[DUP] check_duplicate(%s) : %s", ctx.note_db.id, exc)
        return False, []


def clean_title(title: str) -> str:
    """
    Nettoie le titre pour comparaison fuzzy (dates, underscores).
    """
    return re.sub(r"^\d{6}_?", "", (title or "").replace("_", " ")).lower()
