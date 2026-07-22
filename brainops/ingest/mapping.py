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
    Construit les métadonnées d'une note depuis un manifest audio.

    Raises:
        ValueError: Si le manifest est vide ou mal structuré.
    """
    if not manifest:
        raise ValueError("Manifest audio vide.")

    raw_source = manifest.get("source") or {}
    raw_authors = manifest.get("authors") or []

    if not isinstance(raw_source, Mapping):
        raise ValueError("La section 'source' du manifest est invalide.")

    provider = str(raw_source.get("provider") or "").strip()
    url = str(raw_source.get("url") or "").strip()
    raw_type = raw_source.get("type")

    doc_type = DocumentSemanticType.from_str(raw_type if isinstance(raw_type, str) else None)

    analysis_profile = manifest["analysis_profile"].strip()

    created = str(manifest.get("published_at") or "").strip()
    if not created:
        created = _now_utc_iso()

    absolute_audio = Path("/mnt/user/Zin-progress/Brainops/")
    media_abs = absolute_audio / to_rel(str(media_file_path))

    authors = [author.strip() for author in raw_authors if isinstance(author, str) and author.strip()]

    return NoteMetadata(
        title=str(manifest.get("title") or "").strip(),
        created=created,
        last_modified=_now_utc_iso(),
        source=url,
        author=", ".join(authors),
        doc_type=doc_type,
        analysis_profile=analysis_profile,
        provider=provider,
        media_source=str(media_abs),
        tags=["audio", doc_type.value, analysis_profile],
        status="draft",
    )
