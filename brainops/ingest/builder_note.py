from datetime import UTC, datetime
from pathlib import Path

from brainops.header.header_utils import hash_source
from brainops.models.metadata import DocumentSemanticType
from brainops.models.note import Note
from brainops.utils.logger import LoggerProtocol, ensure_logger


def build_note_shell_from_audio_manifest(
    *,
    title: str,
    file_path: Path,
    source_url: str | None,
    created_at: str | None,
    language: str | None,
    doc_type: DocumentSemanticType,
    analysis_profile: str | None,
    provider: str | None,
    logger: LoggerProtocol | None = None,
) -> Note:
    """
    Construit un objet Note prêt à être inséré en base pour un import audio (status=processing).
    """
    logger = ensure_logger(logger, __name__)
    now_iso = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    safe_title = title.strip() if title else file_path.stem

    return Note(
        id=None,
        parent_id=None,
        title=safe_title,
        file_path=file_path.as_posix(),
        status="processing",
        summary=None,
        source=source_url,
        author=None,
        project=None,
        created_at=created_at or now_iso,
        modified_at=now_iso,
        updated_at=None,
        word_count=0,
        content_hash=None,
        source_hash=hash_source(source_url) if source_url else None,
        lang=(language or "").strip().lower()[:3] if language else None,
        doc_type=doc_type,
        analysis_profile=analysis_profile if analysis_profile else "generic",
    )
