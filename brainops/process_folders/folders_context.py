"""
# process/folders_context.py
"""

from __future__ import annotations

import os
from pathlib import Path

from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.folder_context import FolderContext
from brainops.models.folders import FolderType
from brainops.process_folders.detect_folder_type import detect_folder_type
from brainops.process_import.utils.paths import path_is_inside
from brainops.sql.categs.db_create_categ import (
    get_or_create_category,
    get_or_create_subcategory,
)
from brainops.sql.get_linked.db_get_linked_folders_utils import (
    get_folder_id,
)
from brainops.utils.config import Z_STORAGE_PATH
from brainops.utils.logger import LoggerProtocol, ensure_logger, with_child_logger


def normalize_folder_path(p: str | Path) -> str:
    """
    Chemin absolu POSIX (stable multi-OS).
    """
    return Path(str(p)).as_posix()


@with_child_logger
def add_folder_context(path: str | Path, logger: LoggerProtocol | None = None) -> FolderContext:
    """
    Calcule le contexte d'un dossier (parent, catégories, type).

    Réutilisable par add_folder().
    """
    logger = ensure_logger(logger, __name__)
    category, subcategory, category_id, subcategory_id = (
        None,
        None,
        None,
        None,
    )
    logger.debug("[DEBUG] add_folder_context(%s)", path)

    try:
        p_str = normalize_folder_path(path)
        logger.debug("[DEBUG] add_folder_context p_str normalize_folder_path (%s)", path)

        # parent
        p = Path(p_str)
        parent_path = p.parent.as_posix() if p.parent != p else None
        logger.debug("[DEBUG] add_folder_context parent_path (%s)", parent_path)
        parent_id = get_folder_id(parent_path, logger=logger) if parent_path else None
        logger.debug("[DEBUG] add_folder_context parent_id (%s)", parent_id)

        # type
        ftype = detect_folder_type(p_str)
        parts = p_str.split(os.sep)
        logger.debug("[DEBUG] folder context nb parts: %s", len(parts))
        if path_is_inside(Z_STORAGE_PATH, p_str):
            if len(parts) == 3:
                category = parts[2]
                logger.debug("[DEBUG] part=3 add_folder_context category (%s)", category)
            elif len(parts) == 4:
                category, subcategory = parts[2], parts[3]
                logger.debug("[DEBUG] part=4 add_folder_context category (%s) sub %s", category, subcategory)
            elif len(parts) == 5 and parts[4].lower() == "archives":
                category, subcategory = parts[2], parts[3]
                logger.debug("[DEBUG] part=4 add_folder_context category (%s) sub %s", category, subcategory)
                ftype = FolderType.ARCHIVE
        else:
            if len(parts) == 2:
                category = parts[1]
                logger.debug("[DEBUG] part=1 add_folder_context category (%s)", category)
            elif len(parts) >= 3:
                category, subcategory = parts[1], parts[2]
                logger.debug("[DEBUG] part=2 add_folder_context category (%s) sub %s", category, subcategory)

        if category:
            category_id = get_or_create_category(category, logger=logger)
            logger.debug(f"[DEBUG] category_id: {category_id} {category}")
            if subcategory:
                subcategory_id = get_or_create_subcategory(subcategory, category_id, logger=logger)
                logger.debug(f"[DEBUG] subcategory_id: {subcategory_id} {subcategory}")

        return FolderContext(
            parent_path=parent_path,
            parent_id=parent_id,
            category_id=category_id,
            subcategory_id=subcategory_id,
            category_name=category,
            subcategory_name=subcategory,
            folder_type=ftype,
        )
    except Exception as exc:  # pylint: disable=broad-except
        raise BrainOpsError(
            "KO création folder",
            code=ErrCode.DB,
            ctx={"path": path},
        ) from exc
