"""
io.utils.py — Fonctions ytils centralisées de lecture de notes Obsidian.
"""

from __future__ import annotations

import time

from brainops.io.paths import to_abs
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.types import StrOrPath
from brainops.utils.logger import LoggerProtocol, ensure_logger


def read_note_content(filepath: StrOrPath, *, logger: LoggerProtocol | None = None) -> str:
    """
    Lit le contenu d'une note (UTF-8), avec retry si vide.
    """
    logger = ensure_logger(logger, __name__)
    p = to_abs(filepath)

    max_retries = 5
    delay = 1  # secondes

    for attempt in range(max_retries):
        try:
            logger.debug("[read_note_content] Lecture tentative %d pour %s", attempt + 1, p)
            text = p.read_text(encoding="utf-8")

            if len(text.strip()) > 0:
                logger.debug("[read_note_content] OK (%d chars)", len(text))
                return text
            else:
                logger.warning("[read_note_content] Fichier vide à la tentative %d", attempt + 1)

        except Exception as exc:
            logger.error("[read_note_content] Erreur de lecture : %s", exc)
            if attempt == max_retries - 1:
                raise BrainOpsError("Lecture KO", code=ErrCode.FILEERROR, ctx={"filepath": filepath}) from exc

        time.sleep(delay)

    raise BrainOpsError("Fichier vide après plusieurs tentatives", code=ErrCode.FILEERROR, ctx={"filepath": filepath})
