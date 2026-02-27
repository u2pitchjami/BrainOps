from __future__ import annotations

import json
from pathlib import Path
import re

from brainops.ingest.audio_manifest import AudioManifest, WhisperJSON, WhisperSegment
from brainops.utils.logger import LoggerProtocol, ensure_logger

_SENTENCE_END_RE = re.compile(r"[.!]\s*$")


def generate_markdown_from_whisper(
    whisper_json_path: Path,
    output_md: Path,
    *,
    title: str,
    manifest: AudioManifest,
    audio_file: Path,
    target_words: int = 100,
    max_words: int = 150,
    logger: LoggerProtocol | None = None,
) -> None:
    logger = ensure_logger(logger, __name__)
    with whisper_json_path.open("r", encoding="utf-8") as f:
        data: WhisperJSON = json.load(f)

    markdown = whisper_json_to_markdown(
        data,
        title=title,
        manifest=manifest,
        audio_filename=audio_file.name,
        target_words=target_words,
        max_words=max_words,
    )

    output_md.write_text(markdown, encoding="utf-8")


def whisper_json_to_markdown(
    data: WhisperJSON,
    *,
    title: str,
    manifest: AudioManifest,
    audio_filename: str,
    target_words: int,
    max_words: int,
) -> str:
    segments = data.get("segments")
    if not segments:
        raise ValueError("JSON Whisper invalide : aucun segment trouvé")

    paragraphs = group_whisper_segments(
        segments,
        target_words=target_words,
        max_words=max_words,
    )

    source = manifest["source"]

    lines: list[str] = []

    # --- Frontmatter Brainops / Obsidian ---
    lines.extend(
        [
            "---",
            f"title: {title}",
            f"language: {manifest['language']}",
            f"published_at: {manifest['published_at']}",
            f"source_provider: {source['provider']}",
            f"source_type: {source['type']}",
            f"source_url: {source['url']}",
            f"show: {source['show']}",
            f"authors: {', '.join(manifest.get('authors', []))}",
            f"audio_file: [[{audio_filename}]]",
            "---",
            "",
            "",
        ]
    )

    lines.extend(paragraphs)

    return "\n\n".join(lines).strip() + "\n"


def group_whisper_segments(
    segments: list[WhisperSegment],
    *,
    target_words: int,
    max_words: int,
) -> list[str]:
    paragraphs: list[str] = []
    buffer: list[str] = []
    word_count = 0

    def flush() -> None:
        nonlocal buffer, word_count
        if buffer:
            paragraphs.append(" ".join(buffer).strip())
            buffer = []
            word_count = 0

    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue

        buffer.append(text)
        word_count += len(text.split())

        if word_count >= target_words:
            joined = " ".join(buffer)
            if _SENTENCE_END_RE.search(joined) or word_count >= max_words:
                flush()

    flush()
    return paragraphs
