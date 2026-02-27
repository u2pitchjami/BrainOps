from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Semantic document type (métier)
# ---------------------------------------------------------------------------


class DocumentSemanticType(str, Enum):
    ARTICLE = "article"
    PODCAST = "podcast"
    INTERVIEW = "interview"
    REPORT = "report"
    NOTE = "note"
    UNKNOWN = "unknown"

    @classmethod
    def from_str(cls, value: str | None) -> DocumentSemanticType:
        if not value:
            return cls.UNKNOWN
        normalized = value.strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        return cls.UNKNOWN


# ---------------------------------------------------------------------------
# Metadata principal
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class NoteMetadata:
    title: str = ""
    tags: list[str] = field(default_factory=list)
    summary: str = ""
    category: str = ""
    subcategory: str = ""

    created: str | None = None
    last_modified: str | None = None

    source: str = ""
    author: str = ""
    status: str = "draft"
    project: str = ""

    # --- Nouveaux champs métier ---
    doc_type: DocumentSemanticType = DocumentSemanticType.UNKNOWN
    provider: str = ""
    media_source: str = ""

    # -----------------------------------------------------------------------
    # Constructeurs
    # -----------------------------------------------------------------------

    @classmethod
    def from_yaml_dict(cls, data: Mapping[str, Any] | None) -> NoteMetadata:
        """
        Construit un NoteMetadata à partir d'un dict YAML.

        - Tolère data == None ou data non-mapping.
        - Normalise 'subcategory' / 'sub category'.
        - Normalise 'tags' (liste attendue ; si str CSV, split).
        """

        if not isinstance(data, Mapping):
            return cls()

        def _as_str(x: Any, default: str = "") -> str:
            return default if x is None else str(x)

        # subcategory alias
        subcat = data.get("subcategory", data.get("sub category", ""))

        # tags normalisation
        raw_tags = data.get("tags", [])
        if isinstance(raw_tags, str):
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        elif isinstance(raw_tags, list):
            tags = [str(t).strip() for t in raw_tags if str(t).strip()]
        else:
            tags = []

        # Nouveau : semantic doc type
        doc_type_raw = _as_str(data.get("doc_type") or data.get("type"))
        doc_type = DocumentSemanticType.from_str(doc_type_raw)

        return cls(
            title=_as_str(data.get("title")),
            tags=tags,
            summary=_as_str(data.get("summary")),
            category=_as_str(data.get("category")),
            subcategory=_as_str(subcat),
            created=_as_str(data.get("created")) or None,
            last_modified=_as_str(data.get("last_modified")) or None,
            source=_as_str(data.get("source")),
            author=_as_str(data.get("author")),
            status=_as_str(data.get("status") or "draft"),
            project=_as_str(data.get("project")),
            doc_type=doc_type,
            provider=_as_str(data.get("provider")),
            media_source=_as_str(data.get("media_source")),
        )

    @classmethod
    def from_db_dict(cls, data: dict[str, str | int | None]) -> NoteMetadata:
        """
        Construit un objet à partir des champs DB.
        """

        return cls(
            title=str(data.get("title", "")),
            summary=str(data.get("summary", "")),
            source=str(data.get("source", "")),
            author=str(data.get("author", "")),
            project=str(data.get("project", "")),
            status=str(data.get("status", "draft")),
            created=str(data.get("created_at", "")) or None,
            doc_type=DocumentSemanticType.from_str(str(data.get("doc_type", "")) if data.get("doc_type") else None),
            provider=str(data.get("provider", "")),
            media_source=str(data.get("media_source", "")),
        )

    @classmethod
    def merge(cls, *sources: NoteMetadata) -> NoteMetadata:
        """
        Fusionne plusieurs objets Metadata : priorité à gauche.
        """

        result = cls()
        print(f"result: {result}")

        for source in reversed(sources):
            print(f"source: {source}")
            for field_name in result.__dataclass_fields__:
                print(f"field_name: {field_name}")
                val = getattr(source, field_name)
                print(f"val: {val}")
                if val:
                    setattr(result, field_name, val)
        print("CLASS:", cls)
        print("MODULE:", cls.__module__)
        print("FIELDS:", result.__dataclass_fields__.keys())
        print(f"result: {result}")
        return result

    # -----------------------------------------------------------------------
    # Exporteurs
    # -----------------------------------------------------------------------

    def to_yaml_dict(self) -> dict[str, str | list[str]]:
        return {
            "title": self.title,
            "tags": [str(t).replace(" ", "_") for t in self.tags],
            "summary": self.summary.strip(),
            "category": self.category,
            "sub category": self.subcategory,
            "created": self.created or "",
            "last_modified": self.last_modified or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": self.source,
            "author": self.author,
            "status": self.status,
            "project": self.project,
            # --- nouveaux champs ---
            "doc_type": self.doc_type.value,
            "provider": self.provider,
            "media_source": self.media_source,
        }

    def to_dict(self) -> dict[str, str | list[str]]:
        """
        Export générique (ex: DB, API).
        """
        return self.to_yaml_dict()
