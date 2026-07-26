"""
Construction et export d'une transcription normalisée depuis Whisper.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import re
from typing import Any, NotRequired, TypedDict, cast

import yaml

_SENTENCE_END_RE = re.compile(r"""[.!?…]["'»”’)\]]*$""")


class WhisperSegmentJSON(TypedDict):
    """
    Structure attendue d'un segment dans le JSON Whisper.
    """

    start: NotRequired[float]
    end: NotRequired[float]
    text: NotRequired[str]


class WhisperJSON(TypedDict):
    """
    Sous-ensemble exploité du document JSON produit par Whisper.
    """

    segments: NotRequired[list[WhisperSegmentJSON]]
    language: NotRequired[str]
    text: NotRequired[str]


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    """
    Segment technique validé provenant de Whisper.
    """

    index: int
    start: float
    end: float
    text: str


@dataclass(frozen=True, slots=True)
class TranscriptSentence:
    """
    Phrase reconstruite à partir d'un ou plusieurs segments.
    """

    index: int
    start: float
    end: float
    text: str
    segment_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class TranscriptParagraph:
    """
    Paragraphe construit à partir de plusieurs phrases.
    """

    index: int
    start: float
    end: float
    text: str
    sentence_indexes: tuple[int, ...]

    @property
    def duration_seconds(self) -> float:
        """
        Retourne la durée audio couverte par le paragraphe.
        """
        return max(0.0, self.end - self.start)

    @property
    def word_count(self) -> int:
        """
        Retourne le nombre approximatif de mots.
        """
        return len(self.text.split())


@dataclass(frozen=True, slots=True)
class TranscriptMetadata:
    """
    Métadonnées documentaires de la transcription.
    """

    title: str
    language: str
    audio_filename: str
    source_type: str
    source_provider: str
    source_url: str | None = None
    show: str | None = None
    authors: tuple[str, ...] = ()
    published_at: str | None = None
    analysis_profile: str = "generic"


@dataclass(frozen=True, slots=True)
class ParagraphBuilderConfig:
    """
    Configuration de construction des paragraphes.
    """

    target_sentences: int = 5
    max_sentences: int = 8
    preferred_max_words: int = 180
    max_pause_seconds: float = 2.0

    def validate(self) -> None:
        """
        Valide la cohérence de la configuration.
        """
        if self.target_sentences <= 0:
            raise ValueError("'target_sentences' doit être strictement positif.")

        if self.max_sentences <= 0:
            raise ValueError("'max_sentences' doit être strictement positif.")

        if self.target_sentences > self.max_sentences:
            raise ValueError("'target_sentences' ne peut pas être supérieur à 'max_sentences'.")

        if self.preferred_max_words <= 0:
            raise ValueError("'preferred_max_words' doit être strictement positif.")

        if self.max_pause_seconds < 0:
            raise ValueError("'max_pause_seconds' ne peut pas être négatif.")


@dataclass(frozen=True, slots=True)
class Transcript:
    """
    Représentation normalisée complète d'une transcription.
    """

    metadata: TranscriptMetadata
    segments: tuple[TranscriptSegment, ...]
    sentences: tuple[TranscriptSentence, ...]
    paragraphs: tuple[TranscriptParagraph, ...]
    source_json_path: Path | None = None

    @property
    def duration_seconds(self) -> float:
        """
        Retourne la durée totale connue de la transcription.
        """
        if not self.segments:
            return 0.0

        return max(segment.end for segment in self.segments)

    @property
    def full_text(self) -> str:
        """
        Retourne le texte complet séparé en paragraphes.
        """
        return "\n\n".join(paragraph.text for paragraph in self.paragraphs if paragraph.text)


def load_whisper_json(path: Path) -> WhisperJSON:
    """
    Charge un fichier JSON Whisper.

    Args:
        path: Chemin du fichier JSON.

    Returns:
        Données JSON Whisper.

    Raises:
        FileNotFoundError: Si le fichier n'existe pas.
        OSError: Si le fichier ne peut pas être lu.
        ValueError: Si le JSON est invalide.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Fichier Whisper introuvable : {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            raw_data: object = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON Whisper invalide : {path}") from exc
    except OSError as exc:
        raise OSError(f"Impossible de lire le JSON Whisper : {path}") from exc

    if not isinstance(raw_data, dict):
        raise ValueError("Le JSON Whisper doit contenir un objet à sa racine.")

    return cast(WhisperJSON, raw_data)


def parse_whisper_segments(
    segments: Sequence[WhisperSegmentJSON],
) -> list[TranscriptSegment]:
    """
    Valide et convertit les segments du JSON Whisper.

    Args:
        segments: Segments JSON bruts.

    Returns:
        Segments techniques validés.

    Raises:
        ValueError: Si un segment est invalide.
    """
    parsed_segments: list[TranscriptSegment] = []

    for index, segment in enumerate(segments):
        text = _extract_text(segment, segment_index=index)

        if not text:
            continue

        start = _extract_timestamp(
            segment,
            key="start",
            default=0.0,
            segment_index=index,
        )
        end = _extract_timestamp(
            segment,
            key="end",
            default=start,
            segment_index=index,
        )

        if end < start:
            raise ValueError(f"Segment Whisper {index} invalide : 'end' ({end}) est inférieur à 'start' ({start}).")

        parsed_segments.append(
            TranscriptSegment(
                index=index,
                start=start,
                end=end,
                text=text,
            )
        )

    if not parsed_segments:
        raise ValueError("La transcription Whisper ne contient aucun segment exploitable.")

    return parsed_segments


def rebuild_transcript_sentences(
    segments: Iterable[TranscriptSegment],
) -> list[TranscriptSentence]:
    """
    Reconstruit des phrases depuis les segments techniques Whisper.

    Une phrase est fermée lorsqu'un segment se termine par un signe de
    ponctuation de fin de phrase.

    Args:
        segments: Segments Whisper validés.

    Returns:
        Phrases reconstruites.
    """
    sentences: list[TranscriptSentence] = []

    text_buffer: list[str] = []
    segment_indexes: list[int] = []
    sentence_start: float | None = None
    sentence_end = 0.0

    def flush() -> None:
        nonlocal text_buffer
        nonlocal segment_indexes
        nonlocal sentence_start
        nonlocal sentence_end

        if not text_buffer or sentence_start is None:
            return

        text = _normalize_spaces(" ".join(text_buffer))

        if text:
            sentences.append(
                TranscriptSentence(
                    index=len(sentences),
                    start=sentence_start,
                    end=sentence_end,
                    text=text,
                    segment_indexes=tuple(segment_indexes),
                )
            )

        text_buffer = []
        segment_indexes = []
        sentence_start = None
        sentence_end = 0.0

    for segment in segments:
        if sentence_start is None:
            sentence_start = segment.start

        sentence_end = segment.end
        text_buffer.append(segment.text)
        segment_indexes.append(segment.index)

        if _ends_with_sentence_boundary(segment.text):
            flush()

    # Conserve également une éventuelle dernière phrase sans ponctuation.
    flush()

    return sentences


def build_transcript_paragraphs(
    sentences: Iterable[TranscriptSentence],
    *,
    config: ParagraphBuilderConfig | None = None,
) -> list[TranscriptParagraph]:
    """
    Construit des paragraphes horodatés à partir de phrases.

    Une phrase n'est jamais découpée. Un paragraphe peut être fermé avant
    l'ajout d'une nouvelle phrase en cas de pause significative, de limite
    de phrases atteinte ou de dépassement de la taille préférée.

    Args:
        sentences: Phrases reconstruites.
        config: Configuration optionnelle.

    Returns:
        Paragraphes construits.

    Raises:
        ValueError: Si la configuration est invalide.
    """
    builder_config = config or ParagraphBuilderConfig()
    builder_config.validate()

    paragraphs: list[TranscriptParagraph] = []
    paragraph_sentences: list[TranscriptSentence] = []
    paragraph_word_count = 0
    previous_end: float | None = None

    def flush() -> None:
        nonlocal paragraph_sentences
        nonlocal paragraph_word_count

        if not paragraph_sentences:
            return

        first_sentence = paragraph_sentences[0]
        last_sentence = paragraph_sentences[-1]

        paragraphs.append(
            TranscriptParagraph(
                index=len(paragraphs),
                start=first_sentence.start,
                end=last_sentence.end,
                text=_normalize_spaces(" ".join(sentence.text for sentence in paragraph_sentences)),
                sentence_indexes=tuple(sentence.index for sentence in paragraph_sentences),
            )
        )

        paragraph_sentences = []
        paragraph_word_count = 0

    for sentence in sentences:
        sentence_word_count = len(sentence.text.split())

        pause_seconds = max(0.0, sentence.start - previous_end) if previous_end is not None else 0.0

        has_significant_pause = bool(paragraph_sentences) and pause_seconds >= builder_config.max_pause_seconds

        sentence_limit_reached = len(paragraph_sentences) >= builder_config.max_sentences

        target_reached = len(paragraph_sentences) >= builder_config.target_sentences

        preferred_size_would_be_exceeded = bool(paragraph_sentences) and (
            paragraph_word_count + sentence_word_count > builder_config.preferred_max_words
        )

        should_flush = (
            has_significant_pause or sentence_limit_reached or (target_reached and preferred_size_would_be_exceeded)
        )

        if should_flush:
            flush()

        paragraph_sentences.append(sentence)
        paragraph_word_count += sentence_word_count
        previous_end = sentence.end

        if len(paragraph_sentences) >= builder_config.max_sentences:
            flush()

    flush()

    return paragraphs


def build_transcript(
    data: WhisperJSON,
    *,
    metadata: TranscriptMetadata,
    config: ParagraphBuilderConfig | None = None,
    source_json_path: Path | None = None,
) -> Transcript:
    """
    Construit une transcription normalisée depuis Whisper.

    Args:
        data: Données JSON Whisper.
        metadata: Métadonnées documentaires.
        config: Configuration des paragraphes.
        source_json_path: Chemin facultatif du JSON source.

    Returns:
        Transcription normalisée.

    Raises:
        ValueError: Si les données sont invalides ou vides.
    """
    raw_segments = data.get("segments")

    if not raw_segments:
        raise ValueError("JSON Whisper invalide : aucun segment trouvé.")

    segments = parse_whisper_segments(raw_segments)
    sentences = rebuild_transcript_sentences(segments)
    paragraphs = build_transcript_paragraphs(
        sentences,
        config=config,
    )

    if not sentences:
        raise ValueError("La transcription ne contient aucune phrase exploitable.")

    if not paragraphs:
        raise ValueError("La transcription ne contient aucun paragraphe exploitable.")

    return Transcript(
        metadata=metadata,
        segments=tuple(segments),
        sentences=tuple(sentences),
        paragraphs=tuple(paragraphs),
        source_json_path=source_json_path,
    )


def transcript_to_markdown(transcript: Transcript) -> str:
    """
    Exporte une transcription normalisée au format Markdown.

    Args:
        transcript: Transcription à exporter.

    Returns:
        Contenu Markdown complet.
    """
    frontmatter = _build_frontmatter(transcript.metadata)
    body = "\n\n".join(paragraph.text for paragraph in transcript.paragraphs)

    return f"---\n{frontmatter}---\n\n{body}\n"


def write_transcript_markdown(
    transcript: Transcript,
    output_path: Path,
) -> None:
    """
    Écrit la transcription au format Markdown.

    Args:
        transcript: Transcription normalisée.
        output_path: Destination du fichier Markdown.

    Raises:
        OSError: Si le fichier ne peut pas être écrit.
    """
    markdown = transcript_to_markdown(transcript)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
    except OSError as exc:
        raise OSError(f"Impossible d'écrire la transcription Markdown : {output_path}") from exc


def write_normalized_transcript_json(
    transcript: Transcript,
    output_path: Path,
) -> None:
    """
    Écrit la transcription normalisée au format JSON.

    Ce fichier peut devenir l'artefact de référence pour les embeddings,
    les citations et les traitements ultérieurs.

    Args:
        transcript: Transcription normalisée.
        output_path: Destination du fichier JSON.

    Raises:
        OSError: Si le fichier ne peut pas être écrit.
    """
    payload = {
        "metadata": asdict(transcript.metadata),
        "source_json_path": (str(transcript.source_json_path) if transcript.source_json_path is not None else None),
        "duration_seconds": transcript.duration_seconds,
        "segments": [asdict(segment) for segment in transcript.segments],
        "sentences": [asdict(sentence) for sentence in transcript.sentences],
        "paragraphs": [asdict(paragraph) for paragraph in transcript.paragraphs],
    }

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        raise OSError(f"Impossible d'écrire la transcription normalisée : {output_path}") from exc


def _extract_text(
    segment: Mapping[str, object],
    *,
    segment_index: int,
) -> str:
    """
    Extrait et valide le texte d'un segment Whisper.
    """
    raw_text = segment.get("text", "")

    if not isinstance(raw_text, str):
        raise ValueError(f"Segment Whisper {segment_index} invalide : 'text' doit être une chaîne.")

    return _normalize_spaces(raw_text)


def _extract_timestamp(
    segment: Mapping[str, object],
    *,
    key: str,
    default: float,
    segment_index: int,
) -> float:
    """
    Extrait et valide un timestamp Whisper.
    """
    raw_value = segment.get(key, default)

    if isinstance(raw_value, bool) or not isinstance(
        raw_value,
        int | float,
    ):
        raise ValueError(f"Segment Whisper {segment_index} invalide : '{key}' doit être numérique, reçu {raw_value!r}.")

    value = float(raw_value)

    if not math.isfinite(value):
        raise ValueError(f"Segment Whisper {segment_index} invalide : '{key}' doit être un nombre fini.")

    if value < 0:
        raise ValueError(f"Segment Whisper {segment_index} invalide : '{key}' ne peut pas être négatif.")

    return value


def _normalize_spaces(text: str) -> str:
    """
    Normalise les espaces d'un texte.
    """
    return " ".join(text.split())


def _ends_with_sentence_boundary(text: str) -> bool:
    """
    Indique si le texte se termine par une fin de phrase.
    """
    return _SENTENCE_END_RE.search(text.rstrip()) is not None


def _build_frontmatter(metadata: TranscriptMetadata) -> Any:
    """
    Construit le frontmatter YAML de la transcription.
    """
    frontmatter: dict[str, object] = {
        "title": metadata.title.strip(),
        "language": metadata.language,
        "published_at": metadata.published_at,
        "source_provider": metadata.source_provider,
        "source_type": metadata.source_type,
        "doc_type": metadata.source_type,
        "analysis_profile": metadata.analysis_profile,
        "source_url": metadata.source_url,
        "show": metadata.show,
        "authors": list(metadata.authors),
        "audio_file": f"[[{metadata.audio_filename}]]",
    }

    # Évite d'écrire des propriétés YAML à null.
    cleaned_frontmatter = {key: value for key, value in frontmatter.items() if value is not None}

    return yaml.safe_dump(
        cleaned_frontmatter,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
