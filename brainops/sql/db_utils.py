"""
# sql/db_utils.py
"""

from __future__ import annotations

from typing import Any

from brainops.models.cursor_protocol import DictCursorProtocol, TupleCursorProtocol
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.utils.logger import LoggerProtocol, ensure_logger

# Typing selon ce que pymysql accepte réellement
ParamsType = tuple[Any, ...] | dict[str, Any]


def safe_execute_dict(
    cursor: DictCursorProtocol,
    query: str,
    params: tuple[Any, ...] | dict[str, Any] | None = None,
    logger: LoggerProtocol | None = None,
) -> DictCursorProtocol:
    """
    Exécute une requête après avoir flush le curseur.

    Args:
        cursor: curseur DB conforme au protocole minimal.
        query: requête SQL.
        params: paramètres positionnels (tuple) ou nommés (dict).

    Returns:
        Le même curseur (chaînable avec .fetchone() / .fetchall()).
    """
    logger = ensure_logger(logger, __name__)
    try:
        flush_dict_cursor(cursor, logger=logger)
        if params is not None:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor
    except Exception as exc:
        raise BrainOpsError("Erreur requête DB", code=ErrCode.DB, ctx={"query": query}) from exc


def safe_execute_tuple(
    cursor: TupleCursorProtocol,
    query: str,
    params: tuple[Any, ...] | dict[str, Any] | None = None,
    logger: LoggerProtocol | None = None,
) -> TupleCursorProtocol:
    """
    Exécute une requête après avoir flush le curseur.

    Args:
        cursor: curseur DB conforme au protocole minimal.
        query: requête SQL.
        params: paramètres positionnels (tuple) ou nommés (dict).

    Returns:
        Le même curseur (chaînable avec .fetchone() / .fetchall()).
    """
    logger = ensure_logger(logger, __name__)
    try:
        flush_tuple_cursor(cursor, logger=logger)
        if params is not None:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor
    except Exception as exc:
        raise BrainOpsError("Erreur requête DB", code=ErrCode.DB, ctx={"query": query}) from exc


def flush_tuple_cursor(cursor: TupleCursorProtocol, logger: LoggerProtocol | None = None) -> None:
    """
    Vide proprement le curseur MySQL (utile pour éviter les erreurs 'Unread result found' lors d'appels successifs).

    On itère tant qu'il reste des jeux de résultats non consommés.
    """
    logger = ensure_logger(logger, __name__)
    try:
        while cursor.nextset():
            pass
    except Exception as exc:
        logger.debug("flush_cursor: ignore exception while draining cursor: %s", exc)


def flush_dict_cursor(cursor: DictCursorProtocol, logger: LoggerProtocol | None = None) -> None:
    """
    Vide proprement le curseur MySQL (utile pour éviter les erreurs 'Unread result found' lors d'appels successifs).

    On itère tant qu'il reste des jeux de résultats non consommés.
    """
    logger = ensure_logger(logger, __name__)
    try:
        while cursor.nextset():
            pass
    except Exception as exc:
        logger.debug("flush_cursor: ignore exception while draining cursor: %s", exc)
