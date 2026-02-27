from __future__ import annotations

from collections.abc import Mapping
import hashlib
from pathlib import Path
from typing import Any

from brainops.ingest.audio_duration import extract_audio_duration_seconds
from brainops.models.media import Media
from brainops.models.metadata import DocumentSemanticType
from brainops.utils.logger import LoggerProtocol


def _compute_file_checksum(path: Path) -> str | None:
    """
    Calcule un checksum SHA256 du fichier.

    Retourne None si le fichier n'existe pas.
    """
    if not path.exists() or not path.is_file():
        return None

    sha256 = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def build_media_from_manifest(
    *,
    note_id: int,
    manifest: Mapping[str, Any],
    media_file_path: Path,
    semantic_type: DocumentSemanticType,
    logger: LoggerProtocol | None = None,
) -> Media:
    """
    Construit un objet Media prêt à être inséré en base.
    """

    if not manifest:
        raise ValueError("Manifest vide pour build_media_from_manifest")

    source = manifest.get("source") or {}

    raw_media_type = str(source.get("type", "")).strip().lower()
    provider = str(source.get("provider", "")).strip() or None
    source_url = str(source.get("url", "")).strip() or None

    language = str(manifest.get("language", "")).strip() or None
    published_at = manifest.get("published_at")

    manifest_version = manifest.get("manifest_version")
    duration = extract_audio_duration_seconds(media_file_path, logger=logger)

    file_size = None
    checksum = None

    if media_file_path.exists():
        file_size = media_file_path.stat().st_size
        checksum = _compute_file_checksum(media_file_path)

    return Media(
        id=None,
        note_id=note_id,
        media_type=raw_media_type or "audio",
        semantic_type=semantic_type.value,
        provider=provider,
        source_url=source_url,
        storage_path=media_file_path.as_posix(),
        language=language,
        published_at=published_at,
        duration_seconds=duration,
        file_size_bytes=file_size,
        checksum=checksum,
        manifest_version=manifest_version,
        created_at=None,
    )
