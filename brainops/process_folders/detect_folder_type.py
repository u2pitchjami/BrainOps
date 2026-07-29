"""
# process/folders_context.py
"""

from __future__ import annotations

from brainops.models.folders import FolderType
from brainops.models.note import DocumentSemanticType

PERSONAL_DOCUMENT_TYPES: tuple[DocumentSemanticType, ...] = (
    DocumentSemanticType.OTHER,
    DocumentSemanticType.TUTORIAL,
    DocumentSemanticType.PERSONAL,
    DocumentSemanticType.PROJECT,
)

FOLDER_TO_DOCUMENT_TYPE: dict[FolderType, DocumentSemanticType] = {
    FolderType.PERSONAL: DocumentSemanticType.PERSONAL,
    FolderType.PROJECT: DocumentSemanticType.PROJECT,
    FolderType.STORAGE: DocumentSemanticType.ARTICLE,
    FolderType.TUTORIAL: DocumentSemanticType.TUTORIAL,
    FolderType.OTHER: DocumentSemanticType.OTHER,
}


def detect_folder_type(path: str) -> FolderType:
    """
    Détection par règles simples sur le chemin complet (fallback) → Enum.
    """
    lower = path.lower()
    if "z_storage/" in lower:
        return FolderType.STORAGE
    if "tutos/" in lower:
        return FolderType.TUTORIAL
    if "personal/" in lower:
        return FolderType.PERSONAL
    if "projects/" in lower:
        return FolderType.PROJECT
    if "duplicates/" in lower:
        return FolderType.DUPLICATES
    if "error/" in lower:
        return FolderType.ERROR
    if "imports/" in lower:
        return FolderType.DRAFT
    if "uncategorized/" in lower:
        return FolderType.UNCATEGORIZED
    if "templates/" in lower:
        return FolderType.TEMPLATES
    if "dailynotes/" in lower:
        return FolderType.DAILY_NOTES
    if "gpt/" in lower:
        return FolderType.GPT
    if "z_technical/" in lower:
        return FolderType.TECHNICAL
    return FolderType.OTHER
