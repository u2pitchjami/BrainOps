"""
# models/folder.py
"""

from __future__ import annotations

from enum import StrEnum


class FolderType(StrEnum):
    """
    Miroir de l'ENUM MariaDB.
    """

    STORAGE = "storage"
    SYNTHESIS = "synthesis"
    ARCHIVE = "archive"
    TECHNICAL = "technical"
    PROJECT = "project"
    PERSONAL = "personal"
    TUTORIAL = "tutorial"
    DUPLICATES = "duplicates"
    ERROR = "error"
    DRAFT = "draft"
    UNCATEGORIZED = "uncategorized"
    TEMPLATES = "templates"
    DAILY_NOTES = "daily_notes"
    GPT = "gpt"
    OTHER = "other"

    def __str__(self) -> str:
        return self.value
