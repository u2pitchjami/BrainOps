"""
# process/new_note.py
"""

from __future__ import annotations

import codecs
from datetime import datetime
import hashlib
from pathlib import Path
import re
import shutil
from typing import Any

from brainops.io.paths import to_abs
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.utils.config import DUPLICATES_LOGS, DUPLICATES_PATH
from brainops.utils.logger import (
    LoggerProtocol,
)

# ---------- helpers FS ---------------------------------------------------------


def _normalize_abs_posix(p: str | Path) -> Path:
    return Path(str(p))


def _ensure_duplicates_dir() -> None:
    Path(to_abs(DUPLICATES_PATH)).mkdir(parents=True, exist_ok=True)
    Path(DUPLICATES_LOGS).parent.mkdir(parents=True, exist_ok=True)


def _handle_duplicate_note(file_path: Path, match_info: list[dict[str, Any]], *, logger: LoggerProtocol) -> Path:
    """
    Déplace une note vers DUPLICATES_PATH et journalise les infos.
    """
    logger = logger
    _ensure_duplicates_dir()
    new_path = Path(DUPLICATES_PATH) / file_path.name

    try:
        shutil.move(str(to_abs(file_path)), str(to_abs(new_path)))
        logger.warning("Note déplacée vers 'duplicates' : %s", new_path.as_posix())

        with open(DUPLICATES_LOGS, "a", encoding="utf-8") as log_file:
            log_file.write(f"{datetime.now().isoformat()} - {file_path.name} doublon de {match_info}\n")

        return new_path
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("[DUPLICATE] Échec déplacement vers 'duplicates' : %s", exc)
        return file_path


CHUNK_SIZE = 1024 * 1024  # 1 Mo


def compute_wc_and_hash(fp: Path) -> tuple[int, str | None]:
    """
    Calcule word_count (pour .md/.txt) et sha256 en un seul passage disque.

    - Pour les autres extensions: word_count=0, hash quand même.
    """
    is_text = Path(to_abs(fp)).suffix.lower() in {".md", ".txt"}
    h = hashlib.sha256()
    word_count = 0

    # décodeur texte incrémental (permet de compter les mots sans relire)
    decoder = codecs.getincrementaldecoder("utf-8")(errors="ignore") if is_text else None
    tail = ""  # dernier token potentiel coupé entre deux chunks

    try:
        with Path(to_abs(fp)).open("rb") as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                h.update(chunk)

                if decoder is not None:
                    # on décode ce chunk en texte
                    text = decoder.decode(chunk)
                    if not text:
                        continue
                    buf = tail + text

                    # si le buffer se termine par un espace, aucun mot coupé
                    if buf[-1].isspace():
                        word_count += len(re.findall(r"\S+", buf))
                        tail = ""
                    else:
                        tokens = re.findall(r"\S+", buf)
                        if tokens:
                            word_count += max(0, len(tokens) - 1)
                            tail = tokens[-1]
                        else:
                            # que des espaces/contrôles → rien à compter, tail inchangé
                            pass

            # flush du décodeur pour le dernier fragment (si besoin)
            if decoder is not None:
                rest = decoder.decode(b"", final=True)
                if rest:
                    buf = tail + rest
                    word_count += len(re.findall(r"\S+", buf))
                elif tail:
                    # s'il restait un token partiel non suivi d'espace, on le compte
                    word_count += 1
                tail = ""

        return word_count, h.hexdigest()
    except Exception as exc:
        raise BrainOpsError("Compute wc and hahs KO", code=ErrCode.UNEXPECTED, ctx={"fp": fp}) from exc
