"""
models/media.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any


@dataclass(slots=True, kw_only=True)
class Media:
    """
    Miroir de la table `medias`.
    """

    id: int | None = None
    note_id: int | None = None

    media_type: str
    doc_type: str

    provider: str | None = None
    source_url: str | None = None
    storage_path: str | None = None

    language: str | None = None
    published_at: str | None = None

    duration_seconds: int | None = None
    file_size_bytes: int | None = None
    checksum: str | None = None

    manifest_version: int | None = None

    editorial_context: str | None = None

    created_at: datetime | None = None

    # ------------------- Mapping DB --------------------------------------------

    @classmethod
    def from_row(
        cls,
        row: Mapping[str, Any] | Sequence[Any],
        columns: Sequence[str] | None = None,
    ) -> Media:
        if isinstance(row, Mapping):
            data = row
        else:
            if columns is None:
                raise TypeError("columns est requis quand row est un tuple/sequence")
            data = dict(zip(columns, row, strict=False))

        editorial_context = data.get("editorial_context")

        return cls(
            id=data.get("id"),
            note_id=data.get("note_id"),
            media_type=str(data.get("media_type", "")),
            doc_type=str(data.get("doc_type", "")),
            provider=data.get("provider"),
            source_url=data.get("source_url"),
            storage_path=data.get("storage_path"),
            language=data.get("language"),
            published_at=data.get("published_at"),
            duration_seconds=data.get("duration_seconds"),
            file_size_bytes=data.get("file_size_bytes"),
            checksum=data.get("checksum"),
            manifest_version=data.get("manifest_version"),
            editorial_context=editorial_context,
            created_at=data.get("created_at"),
        )

    def to_insert_params(self) -> tuple[Any, ...]:
        return (
            self.note_id,
            self.media_type,
            self.doc_type,
            self.provider,
            self.source_url,
            self.storage_path,
            self.language,
            self.published_at,
            self.duration_seconds,
            self.file_size_bytes,
            self.checksum,
            self.manifest_version,
            self.editorial_context,
        )


def _load_json_string_list(value: Any) -> list[str]:
    """
    Charge une liste de chaînes depuis une colonne JSON.
    """

    if value is None:
        return []

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []

    if not isinstance(value, list):
        return []

    return [str(item).strip() for item in value if str(item).strip()]
