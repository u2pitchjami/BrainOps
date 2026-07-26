"""
note_reader.py — Fonctions centralisées de lecture de notes Obsidian.
"""

from __future__ import annotations

from typing import Any

import yaml

from brainops.header.extract_yaml_header import extract_yaml_header
from brainops.models.metadata import NoteMetadata
from brainops.models.types import _YAML_FENCE, StrOrPath
from brainops.utils.logger import LoggerProtocol, ensure_logger


def get_yaml(content: str, *, logger: LoggerProtocol | None = None) -> dict[str, Any]:
    logger = ensure_logger(logger, __name__)
    try:
        m = _YAML_FENCE.match(content)
        if m:
            loaded = yaml.safe_load(m.group(1)) or {}
            if isinstance(loaded, dict):
                return loaded
            logger.warning("[get_yaml] YAML n'est pas un dict (%s), fallback {}", type(loaded).__name__)
            return {}
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(f"[get_yaml] Erreur parsing YAML : {exc}")
    return {}


def read_note_body(filepath: StrOrPath, *, logger: LoggerProtocol | None = None) -> str:
    """
    Retourne uniquement le corps de la note (hors YAML).
    """
    _, body = extract_yaml_header(str(filepath), logger=logger)
    return body


def read_metadata(filepath: StrOrPath, *, logger: LoggerProtocol | None = None) -> dict[str, Any]:
    """
    Retourne les métadonnées de l'entête YAML (dict brut).
    """
    logger = ensure_logger(logger, __name__)
    header_lines, _ = extract_yaml_header(str(filepath), logger=logger)
    logger.debug(f"read_metadata header_lines: {header_lines}")
    meta = get_yaml("\n".join(header_lines), logger=logger)
    logger.debug(f"read_metadata metadata: {meta}")
    return meta


def read_metadata_field(filepath: StrOrPath, key: str, *, logger: LoggerProtocol | None = None) -> Any:
    """
    Retourne une seule valeur de métadonnée (ex: "title").
    """
    return read_metadata(filepath, logger=logger).get(key)


def read_metadata_object(filepath: StrOrPath, *, logger: LoggerProtocol | None = None) -> NoteMetadata:
    """
    Retourne un objet NoteMetadata typé à partir de l'entête YAML.
    """
    logger = ensure_logger(logger, __name__)
    meta_dict = read_metadata(filepath, logger=logger)
    logger.debug(f"read_metadata_object metadata: {meta_dict}")
    return NoteMetadata.from_yaml_dict(meta_dict)


def read_note_full(filepath: StrOrPath, *, logger: LoggerProtocol | None = None) -> tuple[NoteMetadata, str]:
    """
    Retourne les métadonnées typées + le corps de la note.

    Utile pour traitements IA, enrichissements, etc.
    """
    logger = ensure_logger(logger, __name__)
    header_lines, body = extract_yaml_header(str(filepath), logger=logger)
    logger.debug(f"read_note_full header_lines: {header_lines}")
    logger.debug(f"read_note_full body: {body}")
    meta = NoteMetadata.from_yaml_dict(get_yaml("\n".join(header_lines)))
    logger.debug(f"read_note_full meta: {meta}")
    return meta, body
