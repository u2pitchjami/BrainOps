"""
# models/folder.py
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class FolderType(StrEnum):
    """
    Miroir de l'ENUM MariaDB.
    """

    STORAGE = "synthesis"
    SYNTHESIS = "synthesis"
    ARCHIVE = "archive"
    TECHNICAL = "technical"
    PROJECT = "project"
    PERSONNAL = "personnal"
    DUPLICATES = "duplicates"
    ERROR = "error"
    DRAFT = "draft"
    UNCATEGORIZED = "uncategorized"
    TEMPLATES = "templates"
    DAILY_NOTES = "daily_notes"
    GPT = "gpt"

    def __str__(self) -> str:
        return self.value


@dataclass(slots=True, kw_only=True)
class Folder:
    """
    Représente une ligne de la table `obsidian_folders`.

    Attributes:
        id: PK auto-incrément (None avant insert).
        name: Nom du dossier (dernier segment).
        path: Chemin complet (absolu, POSIX).
        folder_type: Type logique (Enum).
        parent_id: FK dossier parent (ou None pour racine).
        category_id: FK catégorie (ou None).
        subcategory_id: FK sous-catégorie (ou None).
    """

    id: int | None = None
    name: str
    path: str
    folder_type: FolderType
    parent_id: int | None = None
    category_id: int | None = None
    subcategory_id: int | None = None

    def __post_init__(self) -> None:
        """
        # Normalise le chemin en absolu POSIX
        """
        p = Path(self.path)
        self.path = p.as_posix()
        # Si name vide: déduire depuis le path
        if not self.name:
            self.name = p.name

    # --- Helpers pratiques -----------------------------------------------------

    @property
    def parent_path(self) -> str | None:
        """
        Chemin absolu POSIX du parent, ou None si racine.
        """
        p = Path(self.path)
        par = p.parent
        return par.as_posix() if par != p else None

    def to_upsert_params(
        self,
    ) -> tuple[str, str, str, int | None, int | None, int | None]:
        """
        Paramètres prêts pour un INSERT ...

        ON DUPLICATE KEY UPDATE.
        Ordre: name, path, folder_type, parent_id, category_id, subcategory_id
        """
        return (
            self.name,
            self.path,
            self.folder_type.value,
            self.parent_id,
            self.category_id,
            self.subcategory_id,
        )

    def with_new_path(self, new_path: str) -> Folder:
        """
        Retourne une nouvelle instance avec un nouveau chemin (et name mis à jour).

        parent_id/category/subcategory doivent être recalculés par le service.
        """
        new_p = Path(new_path)
        return Folder(
            id=self.id,
            name=new_p.name,
            path=new_p.as_posix(),
            folder_type=self.folder_type,
            parent_id=self.parent_id,
            category_id=self.category_id,
            subcategory_id=self.subcategory_id,
        )

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Folder:
        """
        Construit depuis un DictCursor (row['id'], ...).
        """
        return cls(
            id=int(row["id"]) if row.get("id") is not None else None,
            name=str(row["name"]),
            path=str(row["path"]),
            folder_type=FolderType(str(row["folder_type"])),
            parent_id=(int(row["parent_id"]) if row.get("parent_id") is not None else None),
            category_id=(int(row["category_id"]) if row.get("category_id") is not None else None),
            subcategory_id=(int(row["subcategory_id"]) if row.get("subcategory_id") is not None else None),
        )
