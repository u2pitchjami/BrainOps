from __future__ import annotations

from pathlib import Path

from brainops.io.note_writer import safe_write
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.metadata import NoteMetadata
from brainops.process_import.join.join_utils import join_metadata_to_note
from brainops.utils.logger import LoggerProtocol, ensure_logger


def join_header_body(
    body: str,
    meta_yaml: NoteMetadata,
    filepath: Path,
    write_file: bool = True,
    logger: LoggerProtocol | None = None,
) -> str:
    """
    Applique `transform` au CORPS d'une note (frontmatter YAML conservé), puis:

      - si write_file=True : écrit le fichier et retourne None
      - sinon : retourne le contenu complet (YAML + body) sous forme de str

    Le transform peut retourner:
      - str : nouveau body
      - (str, dict) : (nouveau body, mises à jour YAML à fusionner)
    """
    logger = ensure_logger(logger, __name__)
    try:
        # 2) Recomposition entête + corps
        final_content = join_metadata_to_note(body, meta_yaml, logger=logger)

        # 4) Écriture ou retour en mémoire
        if write_file:
            success = safe_write(filepath, content=final_content, logger=logger)
            if not success:
                logger.error("[apply_to_note_body] Problème lors de l’écriture de %s", filepath)
            else:
                logger.info("[apply_to_note_body] Note enregistrée : %s", filepath.as_posix())

        return str(final_content)
    except Exception as exc:
        raise BrainOpsError("join body + yaml KO", code=ErrCode.FILEERROR, ctx={"filepath": filepath}) from exc
