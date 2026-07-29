"""
header.extract_yaml_header.
"""

from __future__ import annotations

from brainops.io.read_note import read_note_content
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.utils.logger import LoggerProtocol, ensure_logger


def extract_yaml_header(filepath: str, *, logger: LoggerProtocol | None = None) -> tuple[list[str], str]:
    """
    Sépare le fichier en entête YAML (en lignes) et contenu (corps de note).

    Retourne (header_lines, content_str)
    """
    logger = ensure_logger(logger, __name__)
    logger.debug("[DEBUG] entrée extract_yaml_header: %s", filepath)
    try:
        content = read_note_content(filepath, logger=logger)
        logger.debug("[DEBUG] extract_yaml_header: content=%r", content[:300])
        lines = content.strip().splitlines()
        header_lines: list[str] = []
        content_lines: list[str] = []

        if lines and lines[0].strip() == "---":
            try:
                yaml_end_idx = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
                header_lines = lines[: yaml_end_idx + 1]
                content_lines = lines[yaml_end_idx + 1 :]
            except StopIteration:
                logger.warning("[WARN] En-tête YAML ouvert mais jamais fermé.")
                content_lines = lines
        else:
            content_lines = lines

        body = "\n".join(content_lines)
        logger.debug("[DEBUG] extract_yaml_header: header=%r", header_lines[:50])
        logger.debug("[DEBUG] extract_yaml_header: body=%r", body[:100])
        return header_lines, body
    except FileNotFoundError as exc:  # pylint: disable=broad-except
        raise BrainOpsError(
            "Note absente !!",
            code=ErrCode.NOFILE,
            ctx={"path": filepath},
        ) from exc
    except Exception as exc:  # pylint: disable=broad-except
        raise BrainOpsError(
            "Erreur inattendue exécutrice",
            code=ErrCode.UNEXPECTED,
            ctx={"path": filepath},
        ) from exc
