"""
utils/files.py.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
import re
import time

from brainops.io.paths import to_abs
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.types import StrOrPath
from brainops.utils.logger import LoggerProtocol, ensure_logger


def wait_for_file(
    file_path: StrOrPath,
    timeout: float = 3.0,
    *,
    logger: LoggerProtocol | None = None,
) -> bool:
    """
    Attend que le fichier existe jusqu'à `timeout` secondes.
    """
    logger = ensure_logger(logger, __name__)
    start = time.time()
    path = Path(to_abs(file_path))
    while not path.exists():
        if time.time() - start > timeout:
            logger.debug("[wait_for_file] timeout sur %s", path)
            return False
        time.sleep(0.5)
    return True


def hash_file_content(filepath: StrOrPath) -> str | None:
    """
    SHA-256 du fichier, None en cas d'erreur.
    """
    try:
        with open(to_abs(filepath), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:  # pylint: disable=broad-except
        # logger délégué au caller si besoin
        return None


def copy_file_with_date(
    filepath: StrOrPath,
    destination_folder: StrOrPath,
    *,
    logger: LoggerProtocol | None = None,
) -> Path:
    """
    Copie un fichier en préfixant par la date 'yymmdd_'.

    Retourne le chemin de destination ou None en cas d'erreur.
    """
    logger = ensure_logger(logger, __name__)
    src = Path(to_abs(filepath))
    dst_dir = Path(to_abs(destination_folder))
    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
        stem, ext = src.stem, src.suffix
        date_str = datetime.now().strftime("%y%m%d")
        dst = dst_dir / f"{date_str} {stem}{ext}"
        dst.write_bytes(src.read_bytes())
    except Exception as exc:
        logger.error("[COPY] Échec %s → %s : %s", src, dst_dir, exc)
        raise BrainOpsError("copy_file KO", code=ErrCode.UNEXPECTED, ctx={"filepath": filepath}) from exc
    logger.info("[COPY] OK %s → %s", src, dst)
    return dst


def move_file_with_date(
    filepath: StrOrPath,
    destination_folder: StrOrPath,
    *,
    logger: LoggerProtocol | None = None,
) -> Path:
    """
    Déplace un fichier en préfixant par la date 'yymmdd_'.

    Retourne le nouveau chemin ou None en cas d'erreur.
    """
    logger = ensure_logger(logger, __name__)
    src = Path(to_abs(filepath))
    dst_dir = Path(to_abs(destination_folder))
    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%y%m%d")
        dst = dst_dir / f"{date_str} {src.name}"
        src.replace(dst)
        logger.info("[move] %s → %s", src, dst)
        return dst
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("[move] Échec %s → %s : %s", src, dst_dir, exc)
        raise BrainOpsError("MOVE_file KO", code=ErrCode.UNEXPECTED, ctx={"filepath": filepath}) from exc


def maybe_clean(content: str | list[str], *, force: bool = False) -> str:
    """
    Nettoie *si nécessaire* :

    - list -> join + clean
    - présence de balises HTML problématiques -> clean
    - force=True -> clean systématique
    """
    if force:
        return clean_content(content)

    if isinstance(content, list):
        return clean_content(content)

    if isinstance(content, str) and ("<svg" in content or "<iframe" in content):
        return clean_content(content)

    return content if isinstance(content, str) else "\n".join(map(str, content))


def clean_content(content: str | list[str]) -> str:
    """
    Nettoyage doux (pré-LLM) en conservant les blocs Markdown.
    """
    if isinstance(content, list):
        content = "\n".join(str(line).strip() for line in content)

    # retire balises <svg>...</svg>, bullets anormales, compresse les sauts
    content = re.sub(r"<svg[^>]*>.*?</svg>", "", content, flags=re.DOTALL)
    content = re.sub(r"^- .*\n?", "", content, flags=re.MULTILINE)
    content = re.sub(r"\n\s*\n+", "\n\n", content)

    return content.strip()
