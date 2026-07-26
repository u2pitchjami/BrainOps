"""
# utils/paths.py
"""

from __future__ import annotations

from pathlib import Path

from brainops.utils.logger import LoggerProtocol, ensure_logger


def path_contains_segment(path: str | Path, segment: str) -> bool:
    """
    True si `segment` est un composant du chemin (quelque soit la position).
    """
    try:
        return segment in Path(path).parts
    except Exception:
        return False


def path_is_inside(base: str | Path, target: str | Path) -> bool:
    """
    True si `target` est strictement sous `base` (structure de dossiers).
    """
    try:
        return Path(target).is_relative_to(Path(base))
    except AttributeError:
        # Compat < 3.9
        try:
            return Path(base) in Path(target).parents
        except Exception:
            return False
    except Exception:
        return False


def get_relative_parts(
    folder_path: str | Path,
    base_path: str | Path,
    *,
    logger: LoggerProtocol | None = None,
) -> tuple[str, ...] | None:
    """
    Renvoie les parties relatives de `folder_path` par rapport à `base_path` (None si folder_path n'est pas dans
    base_path).
    """
    logger = ensure_logger(logger, __name__)
    try:
        rel = Path(folder_path).relative_to(Path(base_path))
        logger.debug("[paths] rel : %s", rel)
        return rel.parts
    except ValueError:
        logger.warning("[paths] %s n'est pas dans %s", folder_path, base_path)
        return None
