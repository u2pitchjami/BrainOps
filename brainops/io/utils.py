"""
io.utils.py — Fonctions ytils centralisées de lecture de notes Obsidian.
"""

from __future__ import annotations

from brainops.io.note_reader import read_note_body
from brainops.io.paths import to_abs
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.types import StrOrPath
from brainops.utils.logger import LoggerProtocol, ensure_logger


def count_words(
    content: str | None,
    filepath: StrOrPath | None = None,
    logger: LoggerProtocol | None = None,
) -> int:
    """
    Compte les mots à partir d'une chaîne.
    """
    logger = ensure_logger(logger, __name__)
    if filepath is not None:
        content = read_note_body(to_abs(filepath).as_posix(), logger=logger)

    if not isinstance(content, str):
        logger.warning("[count_words] contenu invalide (attendu str)")
        raise BrainOpsError(
            "❌ content vide ou inexploitable !!",
            code=ErrCode.NOFILE,
            ctx={"path": filepath, "content": content},
        )

    wc = len(content.split())
    logger.debug("[count_words] %d mots", wc)
    return wc
