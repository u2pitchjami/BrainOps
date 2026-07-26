"""
note_writer.py — Fonctions de mise à jour de l'entête YAML des notes Obsidian.
"""

from __future__ import annotations

from collections.abc import Iterable
import os
from pathlib import Path

import yaml

from brainops.header.header_utils import merge_yaml_header, update_yaml_header
from brainops.io.paths import to_abs
from brainops.io.read_note import read_note_content
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.metadata import NoteMetadata
from brainops.models.types import StrOrPath
from brainops.utils.logger import LoggerProtocol, ensure_logger


def safe_write(
    file_path: StrOrPath,
    content: str | Iterable[str],
    *,
    verify_contains: list[str] | None = None,
    logger: LoggerProtocol | None = None,
) -> bool:
    """
    Écrit de façon sûre :

    - supporte str ou liste/iterable de str
    - fsync
    - vérification optionnelle de champs
    """
    logger = ensure_logger(logger, __name__)
    p = Path(to_abs(file_path))
    try:
        with open(p, "w", encoding="utf-8") as f:
            if isinstance(content, str):
                f.write(content)
                logger.debug("[safe_write] write() %d chars → %s", len(content), p)
            else:
                lines = list(content)
                f.writelines(lines)
                logger.debug("[safe_write] writelines() %d lignes → %s", len(lines), p)
            f.flush()
            # fsync pour garantir la persistance disque
            os.fsync(f.fileno())

        if verify_contains:
            written = p.read_text(encoding="utf-8")
            for needle in verify_contains:
                if needle not in written:
                    logger.warning("[safe_write] Champ manquant '%s' dans %s", needle, p)
                    return False
        return True
    except Exception as exc:  # pylint: disable=broad-except
        raise BrainOpsError("write file KO", code=ErrCode.FILEERROR, ctx={"file_path": file_path}) from exc


def write_metadata_to_note(
    filepath: StrOrPath, content: str, metadata: NoteMetadata, *, logger: LoggerProtocol | None = None
) -> bool:
    """
    Remplace complètement l'entête YAML par le contenu de NoteMetadata.
    """
    logger = ensure_logger(logger, __name__)
    filepath = Path(filepath).as_posix()

    try:
        if not content:
            logger.warning("[WARN] Fichier vide ou non trouvé : %s", filepath)
            return False

        # On conserve uniquement le corps
        lines = content.splitlines(True)
        yaml_start, yaml_end = -1, -1
        if lines and lines[0].strip() == "---":
            yaml_start = 0
            yaml_end = next(
                (i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
                -1,
            )
        body_lines = lines[yaml_end + 1 :] if (yaml_start != -1 and yaml_end != -1) else lines

        yaml_dict = metadata.to_yaml_dict()
        yaml_text = yaml.safe_dump(yaml_dict, default_flow_style=False, sort_keys=False, allow_unicode=True)

        new_content = f"---\n{yaml_text}---\n" + "".join(body_lines)
        return safe_write(filepath, content=new_content, logger=logger)

    except Exception as exc:
        logger.exception("[ERREUR] write_metadata_to_note: %s", exc)
        return False


def merge_metadata_in_note(
    filepath: StrOrPath, updates: dict[str, str | int | list[str]], *, logger: LoggerProtocol | None = None
) -> bool:
    """
    Fusionne des métadonnées dans l'entête YAML existant (sans perdre les anciennes).
    """
    logger = ensure_logger(logger, __name__)
    try:
        content = read_note_content(filepath, logger=logger)
        if not content:
            logger.warning("[WARN] Fichier vide ou non trouvé : %s", filepath)
            return False

        new_content = merge_yaml_header(content, updates, logger=logger)
        return safe_write(filepath, content=new_content, logger=logger)

    except Exception as exc:
        logger.exception("[ERREUR] merge_metadata_in_note: %s", exc)
        return False


def update_yaml_field(filepath: StrOrPath, key: str, value: str, *, logger: LoggerProtocol | None = None) -> bool:
    """
    Met à jour un champ unique dans l'entête YAML (écrase sa valeur).
    """
    logger = ensure_logger(logger, __name__)
    from brainops.header.header_utils import get_yaml

    try:
        content = read_note_content(filepath, logger=logger)
        if not content:
            logger.warning("[WARN] Fichier vide ou non trouvé : %s", filepath)
            return False

        meta = get_yaml(content, logger=logger) or {}
        meta[key] = value
        new_content = update_yaml_header(content, meta, logger=logger)
        return safe_write(filepath, content=new_content, logger=logger)

    except Exception as exc:
        logger.exception("[ERREUR] update_yaml_field: %s", exc)
        return False
