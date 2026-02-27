from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from brainops.io.paths import to_rel
from brainops.models.metadata import DocumentSemanticType, NoteMetadata


def _now_utc_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _map_manifest_type_to_semantic(
    raw_type: str | None,
) -> DocumentSemanticType:
    """
    Convertit le type technique du manifest en type métier.
    """

    if not raw_type:
        return DocumentSemanticType.UNKNOWN

    normalized = raw_type.strip().lower()

    if normalized in {"audio", "podcast"}:
        return DocumentSemanticType.PODCAST

    if normalized in {"video", "vidéo"}:
        # Par défaut on considère qu’une vidéo audio-importée
        # correspond à un podcast/interview.
        return DocumentSemanticType.PODCAST

    if normalized in {"article"}:
        return DocumentSemanticType.ARTICLE

    return DocumentSemanticType.UNKNOWN


def build_metadata_from_audio_manifest(
    manifest: Mapping[str, Any],
    *,
    media_file_path: Path,
) -> NoteMetadata:
    """
    Construit un NoteMetadata enrichi à partir d'un manifest audio.
    """

    if not manifest:
        raise ValueError("Manifest audio vide")

    source = manifest.get("source") or {}
    authors = manifest.get("authors") or []

    provider = str(source.get("provider", "")).strip()
    url = str(source.get("url", "")).strip()
    raw_type = source.get("type")

    created = str(manifest.get("published_at") or "")
    if not created:
        created = _now_utc_iso()

    semantic_type = _map_manifest_type_to_semantic(raw_type)
    absolute_audio = Path("/mnt/user/Zin-progress/Brainops/")
    media_abs = absolute_audio / to_rel(str(media_file_path))

    metadata = NoteMetadata(
        title=str(manifest.get("title", "")).strip(),
        created=created,
        last_modified=_now_utc_iso(),
        source=url,
        author=", ".join(a for a in authors if isinstance(a, str)),
        doc_type=semantic_type,
        provider=provider,
        media_source=str(media_abs),
        tags=["audio", semantic_type.value],
        status="draft",
    )

    return metadata
