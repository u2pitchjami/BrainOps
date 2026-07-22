# brainops/ingest/audio_manifest.py

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, NotRequired, TypedDict, cast

import yaml


class SourceInfo(TypedDict):
    """
    Informations décrivant la source de l'audio.
    """

    url: str
    type: str
    provider: str
    show: str


class AudioManifest(TypedDict):
    """
    Structure validée d'un manifest audio BrainOps.
    """

    manifest_version: int
    source: SourceInfo
    title: str
    language: str
    published_at: str
    authors: list[str]
    analysis_profile: str
    editorial_context: NotRequired[str]


class WhisperSegment(TypedDict):
    """
    Segment textuel retourné par Whisper.
    """

    text: str


class WhisperMetadata(TypedDict, total=False):
    """
    Métadonnées optionnelles retournées par Whisper.
    """

    language: str
    duration: float
    audio_file: str


class WhisperJSON(TypedDict):
    """
    Structure minimale du fichier JSON produit par Whisper.
    """

    segments: list[WhisperSegment]


def require_date_string(
    data: dict[str, Any],
    key: str,
    *,
    parent: str = "manifest",
) -> str:
    """
    Récupère et valide une date au format ISO ``YYYY-MM-DD``.

    Args:
        data: Dictionnaire contenant la valeur.
        key: Nom du champ à valider.
        parent: Nom de la section parente utilisé dans les erreurs.

    Returns:
        Date normalisée au format ISO.

    Raises:
        ValueError: Si la valeur est absente ou invalide.
    """
    value = data.get(key)

    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, str):
        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError(f"Le champ '{parent}.{key}' doit être une date non vide.")

        try:
            parsed_date = date.fromisoformat(cleaned_value)
        except ValueError as exc:
            raise ValueError(f"Le champ '{parent}.{key}' doit être au format YYYY-MM-DD.") from exc

        return parsed_date.isoformat()

    raise ValueError(f"Le champ '{parent}.{key}' doit être une date au format YYYY-MM-DD.")


def require_string(
    data: dict[str, Any],
    key: str,
    *,
    parent: str = "manifest",
) -> str:
    """
    Récupère et valide une chaîne obligatoire.

    Args:
        data: Dictionnaire contenant la valeur.
        key: Nom du champ à valider.
        parent: Nom de la section parente utilisé dans les erreurs.

    Returns:
        Chaîne nettoyée.

    Raises:
        ValueError: Si la valeur est absente, invalide ou vide.
    """
    value = data.get(key)

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Le champ '{parent}.{key}' doit être une chaîne non vide.")

    return value.strip()


def optional_string(
    data: dict[str, Any],
    key: str,
    *,
    parent: str = "manifest",
) -> str | None:
    """
    Récupère et valide une chaîne optionnelle.

    Une chaîne vide ou composée uniquement d'espaces est convertie en
    ``None``.

    Args:
        data: Dictionnaire contenant la valeur.
        key: Nom du champ à valider.
        parent: Nom de la section parente utilisé dans les erreurs.

    Returns:
        Chaîne nettoyée ou ``None``.

    Raises:
        ValueError: Si la valeur est présente mais n'est pas une chaîne.
    """
    value = data.get(key)

    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(f"Le champ '{parent}.{key}' doit être une chaîne.")

    cleaned_value = value.strip()
    return cleaned_value or None


def validate_source(raw_source: object) -> SourceInfo:
    """
    Valide la section ``source`` du manifest.

    Args:
        raw_source: Valeur brute issue du YAML.

    Returns:
        Source validée.

    Raises:
        ValueError: Si la structure ou un champ est invalide.
    """
    if not isinstance(raw_source, dict):
        raise ValueError("Le champ 'source' doit être un objet YAML.")

    source_data = cast(dict[str, Any], raw_source)

    return SourceInfo(
        url=require_string(source_data, "url", parent="source"),
        type=require_string(source_data, "type", parent="source"),
        provider=require_string(source_data, "provider", parent="source"),
        show=require_string(source_data, "show", parent="source"),
    )


# def validate_analysis(raw_analysis: object) -> AnalysisInfo:
#     """
#     Valide la section optionnelle ``analysis`` du manifest.

#     Cette section référence uniquement la catégorisation de la note, le
#     profil d'analyse à charger et le contexte éditorial propre au média.

#     Les paramètres comme l'objectif, la perspective ou les instructions
#     appartiennent au profil YAML et ne doivent pas être dupliqués ici.

#     Args:
#         raw_analysis: Valeur brute issue du YAML.

#     Returns:
#         Configuration d'analyse validée.

#     Raises:
#         ValueError: Si la structure ou un champ est invalide.
#     """
#     if not isinstance(raw_analysis, dict):
#         raise ValueError("Le champ 'analysis' doit être un objet YAML.")

#     analysis_data = cast(dict[str, Any], raw_analysis)

#     analysis = AnalysisInfo(
#         analysis_profile=require_string(
#             analysis_data,
#             "analysis_profile",
#             parent="analysis",
#         ),
#     )

#     context = optional_string(
#         analysis_data,
#         "context",
#         parent="analysis",
#     )

#     if context is not None:
#         analysis["context"] = context

#     return analysis


def validate_authors(raw_authors: object) -> list[str]:
    """
    Valide la liste des auteurs ou intervenants.

    Args:
        raw_authors: Valeur brute issue du YAML.

    Returns:
        Liste nettoyée des auteurs.

    Raises:
        ValueError: Si la valeur n'est pas une liste valide.
    """
    if not isinstance(raw_authors, list):
        raise ValueError("Le champ 'authors' doit être une liste.")

    authors: list[str] = []

    for index, author in enumerate(raw_authors):
        if not isinstance(author, str) or not author.strip():
            raise ValueError(f"L'auteur à l'index {index} doit être une chaîne non vide.")

        authors.append(author.strip())

    if not authors:
        raise ValueError("Le manifest doit contenir au moins un auteur ou intervenant.")

    return authors


def load_manifest(path: Path) -> AudioManifest:
    """
    Charge et valide un manifest audio YAML.

    Args:
        path: Chemin du manifest.

    Returns:
        Manifest validé et normalisé.

    Raises:
        FileNotFoundError: Si le fichier n'existe pas.
        OSError: Si le fichier ne peut pas être lu.
        ValueError: Si le YAML ou sa structure sont invalides.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Manifest introuvable : {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            raw_data: object = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise ValueError(f"Le fichier YAML est invalide : {path}") from exc
    except OSError as exc:
        raise OSError(f"Impossible de lire le manifest : {path}") from exc

    if not isinstance(raw_data, dict):
        raise ValueError(f"Le manifest doit contenir un objet YAML : {path}")

    data = cast(dict[str, Any], raw_data)

    manifest_version = data.get("manifest_version")

    # bool hérite de int en Python : on l'exclut explicitement.
    if isinstance(manifest_version, bool) or not isinstance(
        manifest_version,
        int,
    ):
        raise ValueError("Le champ 'manifest_version' doit être un entier.")

    manifest = AudioManifest(
        manifest_version=manifest_version,
        source=validate_source(data.get("source")),
        title=require_string(data, "title"),
        language=require_string(data, "language"),
        published_at=require_date_string(data, "published_at"),
        authors=validate_authors(data.get("authors")),
        analysis_profile=require_string(data, "analysis_profile"),
    )

    raw_editorial_context = data.get("editorial_context")

    if raw_editorial_context is not None:
        if not isinstance(raw_editorial_context, str):
            raise ValueError("'editorial_context' doit être une chaîne de caractères.")

        editorial_context = raw_editorial_context.strip()

        if editorial_context:
            manifest["editorial_context"] = editorial_context

    return manifest
