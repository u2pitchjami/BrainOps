"""
# models/media.py
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True, kw_only=True)
class Media:
    """
    Miroir de la table `medias`.
    """

    id: int | None = None
    note_id: int | None = None

    media_type: str
    semantic_type: str

    provider: str | None = None
    source_url: str | None = None
    storage_path: str | None = None

    language: str | None = None
    published_at: str | None = None

    duration_seconds: int | None = None
    file_size_bytes: int | None = None
    checksum: str | None = None

    manifest_version: int | None = None
    created_at: datetime | None = None

    # ------------------- Mapping DB --------------------------------------------

    @classmethod
    def from_row(
        cls,
        row: Mapping[str, Any] | Sequence[Any],
        columns: Sequence[str] | None = None,
    ) -> Media:
        if isinstance(row, Mapping):
            d = row
        else:
            if columns is None:
                raise TypeError("columns est requis quand row est un tuple/sequence")
            d = dict(zip(columns, row, strict=False))

        return cls(
            id=d.get("id"),
            note_id=d.get("note_id"),
            media_type=str(d.get("media_type", "")),
            semantic_type=str(d.get("semantic_type", "")),
            provider=d.get("provider"),
            source_url=d.get("source_url"),
            storage_path=d.get("storage_path"),
            language=d.get("language"),
            published_at=d.get("published_at"),
            duration_seconds=d.get("duration_seconds"),
            file_size_bytes=d.get("file_size_bytes"),
            checksum=d.get("checksum"),
            manifest_version=d.get("manifest_version"),
            created_at=d.get("created_at"),
        )

    def to_insert_params(self) -> tuple[Any, ...]:
        return (
            self.note_id,
            self.media_type,
            self.semantic_type,
            self.provider,
            self.source_url,
            self.storage_path,
            self.language,
            self.published_at,
            self.duration_seconds,
            self.file_size_bytes,
            self.checksum,
            self.manifest_version,
        )
