from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, cast

import yaml

from brainops.ingest.audio_manifest import (
    AudioManifest,
    WhisperJSON,
    WhisperSegment,
)
from brainops.utils.logger import LoggerProtocol, ensure_logger

_SENTENCE_END_RE = re.compile(r"[.!?…]\s*$")


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
    """
    Génère une note Markdown à partir d'un fichier JSON Whisper.

    Args:
        whisper_json_path: Chemin du fichier JSON produit par Whisper.
        output_md: Chemin de la note Markdown à générer.
        title: Titre de la note.
        manifest: Manifest audio validé.
        audio_file: Chemin du fichier audio associé.
        target_words: Taille cible d'un paragraphe.
        max_words: Taille maximale d'un paragraphe.
        logger: Logger optionnel.

    Raises:
        FileNotFoundError: Si le JSON Whisper n'existe pas.
        OSError: Si un fichier ne peut pas être lu ou écrit.
        ValueError: Si le JSON Whisper ou les paramètres sont invalides.
    """
    current_logger = ensure_logger(logger, __name__)

    if not whisper_json_path.is_file():
        raise FileNotFoundError(f"Fichier JSON Whisper introuvable : {whisper_json_path}")

    try:
        with whisper_json_path.open("r", encoding="utf-8") as file:
            raw_data: object = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Le fichier JSON Whisper est invalide : {whisper_json_path}") from exc
    except OSError as exc:
        raise OSError(f"Impossible de lire le fichier JSON Whisper : {whisper_json_path}") from exc

    if not isinstance(raw_data, dict):
        raise ValueError("Le JSON Whisper doit contenir un objet à sa racine.")

    data = cast(WhisperJSON, raw_data)

    markdown = whisper_json_to_markdown(
        data,
        title=title,
        manifest=manifest,
        audio_filename=audio_file.name,
        target_words=target_words,
        max_words=max_words,
    )

    try:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(markdown, encoding="utf-8")
    except OSError as exc:
        raise OSError(f"Impossible d'écrire la note Markdown : {output_md}") from exc

    current_logger.info(
        "Note Markdown générée : %s",
        output_md,
    )


def whisper_json_to_markdown(
    data: WhisperJSON,
    *,
    title: str,
    manifest: AudioManifest,
    audio_filename: str,
    target_words: int,
    max_words: int,
) -> str:
    """
    Convertit une transcription Whisper en note Markdown BrainOps.

    Args:
        data: Données Whisper validées.
        title: Titre de la note.
        manifest: Manifest audio validé.
        audio_filename: Nom du fichier audio associé.
        target_words: Taille cible d'un paragraphe.
        max_words: Taille maximale d'un paragraphe.

    Returns:
        Contenu Markdown complet.

    Raises:
        ValueError: Si la transcription ou les paramètres sont invalides.
    """
    if target_words <= 0:
        raise ValueError("'target_words' doit être strictement positif.")

    if max_words <= 0:
        raise ValueError("'max_words' doit être strictement positif.")

    if target_words > max_words:
        raise ValueError("'target_words' ne peut pas être supérieur à 'max_words'.")

    segments = data.get("segments")

    if not segments:
        raise ValueError("JSON Whisper invalide : aucun segment trouvé.")

    paragraphs = group_whisper_segments(
        segments,
        target_words=target_words,
        max_words=max_words,
    )

    if not paragraphs:
        raise ValueError("La transcription Whisper ne contient aucun texte exploitable.")

    frontmatter = build_audio_frontmatter(
        manifest=manifest,
        title=title,
        audio_filename=audio_filename,
    )

    markdown_body = "\n\n".join(paragraphs)

    return f"---\n{frontmatter}---\n\n{markdown_body}\n"


def build_audio_frontmatter(
    *,
    manifest: AudioManifest,
    title: str,
    audio_filename: str,
) -> Any:
    """
    Construit le frontmatter YAML d'une note audio.

    ``source.type`` décrit le type documentaire, par exemple ``podcast``.
    ``analysis.analysis_profile`` décrit la nature du contenu, par exemple
    ``debate`` ou ``interview``.
    """
    source = manifest["source"]

    frontmatter: dict[str, Any] = {
        "title": title.strip(),
        "language": manifest["language"],
        "published_at": manifest["published_at"],
        "source_provider": source["provider"],
        "source_type": source["type"],
        "doc_type": source["type"],
        "analysis_profile": manifest.get("analysis_profile", "generic"),
        "source_url": source["url"],
        "show": source["show"],
        "authors": manifest.get("authors", []),
        "audio_file": f"[[{audio_filename}]]",
    }

    return yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )


def group_whisper_segments(
    segments: list[WhisperSegment],
    *,
    target_words: int,
    max_words: int,
) -> list[str]:
    """
    Regroupe les segments Whisper en paragraphes lisibles.

    Un paragraphe est fermé après avoir atteint ``target_words`` lorsqu'une
    fin de phrase est détectée, ou dès que ``max_words`` est atteint.
    """
    paragraphs: list[str] = []
    buffer: list[str] = []
    word_count = 0

    def flush() -> None:
        nonlocal buffer, word_count

        if not buffer:
            return

        paragraph = " ".join(buffer).strip()

        if paragraph:
            paragraphs.append(paragraph)

        buffer = []
        word_count = 0

    for segment in segments:
        text = segment.get("text", "").strip()

        if not text:
            continue

        buffer.append(text)
        word_count += len(text.split())

        if word_count < target_words:
            continue

        joined_text = " ".join(buffer)

        if _SENTENCE_END_RE.search(joined_text) or word_count >= max_words:
            flush()

    flush()

    return paragraphs
