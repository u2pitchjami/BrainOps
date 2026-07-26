"""
# models/note.py
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum  # py>=3.11
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Semantic document type (métier)
# ---------------------------------------------------------------------------


class DocumentSemanticType(StrEnum):
    """
    Type éditorial ou support principal de la note.
    """

    ARTICLE = "article"
    TUTORIAL = "tutorial"
    PERSONAL = "personal"
    PROJECT = "project"
    PODCAST = "podcast"
    VIDEO = "video"
    NOTE = "note"
    UNKNOWN = "unknown"

    @classmethod
    def from_str(cls, value: str | None) -> DocumentSemanticType:
        """
        Construit un type documentaire depuis une chaîne.
        """
        if not value:
            return cls.UNKNOWN

        normalized = value.strip().lower()

        aliases = {
            "audio": cls.PODCAST,
            "podcast": cls.PODCAST,
            "video": cls.VIDEO,
            "vidéo": cls.VIDEO,
            "article": cls.ARTICLE,
            "tutorial": cls.TUTORIAL,
            "tutoriel": cls.TUTORIAL,
            "personal": cls.PERSONAL,
            "personnel": cls.PERSONAL,
            "project": cls.PROJECT,
            "projet": cls.PROJECT,
            "note": cls.NOTE,
        }

        return aliases.get(normalized, cls.UNKNOWN)


@dataclass(slots=True, kw_only=True)
class Note:
    """
    Miroir de la table `obsidian_notes`.

    Champs transients (non persistés) indiqués en commentaires.
    """

    id: int | None = None
    parent_id: int | None = None

    title: str
    file_path: str

    status: str | None = None
    summary: str | None = None
    source: str | None = None
    author: str | None = None
    project: str | None = None

    created_at: str | None = None
    modified_at: str | None = None
    updated_at: datetime | None = None  # gérée par DB (timestamp ON UPDATE)

    word_count: int = 0
    content_hash: str | None = None
    source_hash: str | None = None
    lang: str | None = None  # 3 lettres (ex: "fr", "en")
    doc_type: DocumentSemanticType = DocumentSemanticType.UNKNOWN
    analysis_profile: str = "generic"

    media_id: int | None = None

    # ---- transients (non stockés) ---------------------------------------------
    name: str = field(init=False, repr=False)  # basename dérivé de file_path
    ext: str = field(init=False, repr=False)  # extension dérivée

    def __post_init__(self) -> None:
        """
        # Normaliser le chemin en absolu POSIX
        """
        p = Path(self.file_path)
        self.file_path = p.as_posix()
        self.name = p.name
        self.ext = p.suffix.lower().lstrip(".")

        # Langue sur 3 chars (si fournie)
        if self.lang:
            self.lang = self.lang.strip().lower()[:3]

        # Sécurité: word_count >= 0
        if self.word_count is None or self.word_count < 0:
            self.word_count = 0

    # ------------------- Mapping DB --------------------------------------------

    @classmethod
    def from_row(
        cls,
        row: Mapping[str, Any] | Sequence[Any],
        columns: Sequence[str] | None = None,
    ) -> Note:
        """
        Accepte:
          - un mapping (dict/Row) avec des clés => direct
          - une séquence (tuple) + `columns` pour zipper
        """
        if isinstance(row, Mapping):
            d = row
        else:
            if columns is None:
                raise TypeError("columns est requis quand row est un tuple/sequence")
            d = dict(zip(columns, row, strict=False))

        return cls(
            id=d.get("id"),
            parent_id=d.get("parent_id"),
            title=str(d.get("title", "")),
            file_path=str(d.get("file_path", "")),
            status=d.get("status"),
            summary=d.get("summary"),
            source=d.get("source"),
            author=d.get("author"),
            project=d.get("project"),
            created_at=d.get("created_at"),
            modified_at=d.get("modified_at"),
            updated_at=d.get("updated_at"),
            word_count=int(d.get("word_count", 0) or 0),
            content_hash=d.get("content_hash"),
            source_hash=d.get("source_hash"),
            lang=d.get("lang"),
            media_id=d.get("media_id"),
            doc_type=DocumentSemanticType.from_str(d.get("doc_type")),
            analysis_profile=str(d.get("analysis_profile", "generic")),
        )

    def to_upsert_params(self) -> tuple[Any, ...]:
        """
        Ordre exactement aligné sur l'INSERT ci-dessous (DAO).
        """
        return (
            self.parent_id,
            self.title,
            self.file_path,
            self.status,
            self.summary,
            self.source,
            self.author,
            self.project,
            self.created_at,
            self.modified_at,
            self.word_count,
            self.content_hash,
            self.source_hash,
            self.lang,
            self.media_id,
            self.doc_type.value,
            self.analysis_profile,
        )
