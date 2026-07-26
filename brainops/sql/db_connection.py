# sql/db_connection.py

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

import pymysql
from pymysql.connections import Connection
from pymysql.cursors import DictCursor

from brainops.models.cursor_protocol import DictCursorProtocol, TupleCursorProtocol
from brainops.models.db_config import DB_CONFIG
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.utils.logger import LoggerProtocol, ensure_logger


def get_dict_cursor(conn: Connection) -> DictCursorProtocol:
    return cast(DictCursorProtocol, conn.cursor(DictCursor))


def get_tuple_cursor(conn: Connection) -> TupleCursorProtocol:
    return cast(TupleCursorProtocol, conn.cursor())


def get_db_connection(
    logger: LoggerProtocol | None = None,
) -> Connection:
    """
    Ouvre une connexion MySQL à partir de la config centralisée (.env chargée par utils.config).
    """
    logger = ensure_logger(logger, __name__)
    try:
        conn = pymysql.connect(**DB_CONFIG)
    except pymysql.MySQLError as exc:
        raise BrainOpsError("Erreur de connection DB", code=ErrCode.DB, ctx={"db": "db"}) from exc
    return conn


@contextmanager
def db_conn(*, autocommit: bool = False, logger: LoggerProtocol | None = None) -> Iterator[Connection]:
    """
    Ouvre une connexion, gère commit/rollback/close en 1 seul endroit.
    """
    logger = ensure_logger(logger, __name__)
    conn = get_db_connection(logger=logger)
    conn.autocommit(autocommit)  # ✅ méthode et non attribut
    try:
        yield conn
        if not autocommit:
            conn.commit()
    except Exception:  # pylint: disable=broad-except
        if not autocommit:
            try:
                conn.rollback()
            except Exception:  # pylint: disable=broad-except
                logger.warning("Rollback failed", exc_info=True)
        raise
    finally:
        try:
            conn.close()
        except pymysql.err.Error as exc:
            if "Already closed" not in str(exc):
                logger.warning("Close failed: %s", exc)
