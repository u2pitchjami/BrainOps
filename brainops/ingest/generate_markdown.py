from pathlib import Path

from brainops.ingest.audio_manifest import (
    AudioManifest,
)
from brainops.ingest.transcript import (
    ParagraphBuilderConfig,
    Transcript,
    TranscriptMetadata,
    build_transcript,
    load_whisper_json,
    write_normalized_transcript_json,
    write_transcript_markdown,
)
from brainops.utils.logger import LoggerProtocol, ensure_logger


def generate_markdown_from_whisper(
    whisper_json_path: Path,
    output_md: Path,
    *,
    title: str,
    manifest: AudioManifest,
    audio_file: Path,
    normalized_json_path: Path | None = None,
    logger: LoggerProtocol | None = None,
) -> Transcript:
    """
    Normalise une transcription Whisper puis génère ses représentations.
    """
    current_logger = ensure_logger(logger, __name__)

    source = manifest["source"]

    metadata = TranscriptMetadata(
        title=title,
        language=manifest["language"],
        published_at=manifest["published_at"],
        source_provider=source["provider"],
        source_type=source["type"],
        source_url=source["url"],
        show=source["show"],
        authors=tuple(manifest.get("authors", [])),
        audio_filename=audio_file.name,
        analysis_profile=manifest.get(
            "analysis_profile",
            "generic",
        ),
    )

    config = ParagraphBuilderConfig(
        target_sentences=5,
        max_sentences=8,
        preferred_max_words=180,
        max_pause_seconds=2.0,
    )

    whisper_data = load_whisper_json(whisper_json_path)

    transcript = build_transcript(
        whisper_data,
        metadata=metadata,
        config=config,
        source_json_path=whisper_json_path,
    )

    write_transcript_markdown(
        transcript,
        output_md,
    )

    if normalized_json_path is not None:
        write_normalized_transcript_json(
            transcript,
            normalized_json_path,
        )

    current_logger.info(
        ("Transcription générée : markdown=%s, segments=%d, phrases=%d, paragraphes=%d"),
        output_md,
        len(transcript.segments),
        len(transcript.sentences),
        len(transcript.paragraphs),
    )

    return transcript
