"""
utils/files.py.
"""

from __future__ import annotations

import yaml

from brainops.models.metadata import NoteMetadata
from brainops.utils.logger import LoggerProtocol, ensure_logger


def join_metadata_to_note(body: str, metadata: NoteMetadata, *, logger: LoggerProtocol | None = None) -> str:
    """
    Remplace complètement l'entête YAML par le contenu de NoteMetadata.
    """
    logger = ensure_logger(logger, __name__)
    try:
        # On conserve uniquement le corps
        lines = body.splitlines(True)
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
        return new_content

    except Exception as exc:
        logger.exception("[ERREUR] write_metadata_to_note: %s", exc)
        return " "


def join_yaml_and_body(
    header_lines: NoteMetadata,
    body: str,
    *,
    logger: LoggerProtocol | None = None,
) -> str:
    """
    Recompose un document à partir de l'entête YAML (lignes) et du corps.

    - Accepte header_lines avec ou sans délimiteurs '---'
    - Normalise le frontmatter sous la forme:
        ---\n<yaml>\n---\n\n<body>\n
    - Évite la prolifération de lignes vides (exactement une entre YAML et corps)
    - Ajoute toujours un newline final.

    Args:
        header_lines: L'entête YAML en lignes (tel que renvoyé par split/parse).
        body: Le corps de la note (texte, sans l'entête).
        logger: Logger optionnel.

    Returns:
        Le contenu complet normalisé (str).
    """
    log = ensure_logger(logger, __name__)

    if not header_lines:
        return body.strip() + "\n"

    lines = [ln.rstrip("\r\n") for ln in str(header_lines)]
    if lines:
        lines[0] = lines[0].lstrip("\ufeff")  # BOM éventuel

    has_start = bool(lines and lines[0].strip() == "---")
    end_idx = None
    if has_start:
        for i, ln in enumerate(lines[1:], start=1):
            if ln.strip() == "---":
                end_idx = i
                break

    if has_start and end_idx is not None:
        inner = lines[1:end_idx]
    else:
        if has_start and end_idx is None:
            log.warning("[join_yaml_and_body] Entête YAML ouvert mais non fermé, normalisation.")
            inner = lines[1:]
        else:
            inner = lines

    yaml_text = "\n".join(inner).strip()
    frontmatter = f"---\n{yaml_text}\n---\n"
    body_clean = body.lstrip("\r\n").strip()
    return f"{frontmatter}\n{body_clean}\n"
