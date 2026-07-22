from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import yaml

from brainops.analysis.config import AnalysisConfig


class AnalysisProfileError(ValueError):
    """
    Erreur liée au chargement ou à la validation d'un profil.
    """


def _read_optional_string(
    data: Mapping[str, Any],
    key: str,
) -> str | None:
    value = data.get(key)

    if value is None:
        return None

    if not isinstance(value, str):
        raise AnalysisProfileError(f"Le champ '{key}' doit être une chaîne.")

    cleaned = value.strip()
    return cleaned or None


def _read_string_list(
    data: Mapping[str, Any],
    key: str,
) -> list[str]:
    value = data.get(key, [])

    if value is None:
        return []

    if not isinstance(value, list):
        raise AnalysisProfileError(f"Le champ '{key}' doit être une liste.")

    result: list[str] = []

    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise AnalysisProfileError(f"Le champ '{key}' contient une valeur invalide à l'index {index}.")

        cleaned = item.strip()
        if cleaned:
            result.append(cleaned)

    return result


def load_analysis_profile(
    profile_name: str,
    *,
    profiles_dir: Path,
) -> AnalysisConfig:
    """
    Charge et valide un profil d'analyse YAML.
    """

    normalized_name = profile_name.strip().lower() or "generic"

    if not normalized_name.replace("_", "").replace("-", "").isalnum():
        raise AnalysisProfileError(f"Nom de profil invalide : {profile_name!r}")

    profile_path = profiles_dir / f"{normalized_name}.yaml"

    if not profile_path.is_file():
        raise FileNotFoundError(f"Profil d'analyse introuvable : {profile_path}")

    try:
        with profile_path.open("r", encoding="utf-8") as file:
            raw_data: object = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise AnalysisProfileError(f"YAML invalide dans le profil '{normalized_name}'.") from exc
    except OSError as exc:
        raise AnalysisProfileError(f"Impossible de lire le profil '{normalized_name}'.") from exc

    if not isinstance(raw_data, Mapping):
        raise AnalysisProfileError(f"Le profil '{normalized_name}' doit contenir un objet YAML.")

    data = cast(Mapping[str, Any], raw_data)

    version = data.get("profile_version", 1)
    if not isinstance(version, int):
        raise AnalysisProfileError("Le champ 'profile_version' doit être un entier.")

    declared_name = data.get("name", normalized_name)
    if not isinstance(declared_name, str):
        raise AnalysisProfileError("Le champ 'name' doit être une chaîne.")

    return AnalysisConfig(
        profile=declared_name.strip().lower() or normalized_name,
        selection_mode=_read_selection_mode(data),
        objective=_read_optional_string(data, "objective"),
        perspective=_read_optional_string(data, "perspective"),
        instructions=_read_string_list(data, "instructions"),
        reflection_questions=_read_string_list(
            data,
            "reflection_questions",
        ),
    )


SUPPORTED_SELECTION_MODES: frozenset[str] = frozenset(
    {
        "quick",
        "standard",
        "diverse",
        "audit",
        "gpt",
    }
)


def _read_selection_mode(
    data: Mapping[str, Any],
) -> str:
    raw_value = data.get("selection_mode", "standard")

    if not isinstance(raw_value, str):
        raise AnalysisProfileError("Le champ 'selection_mode' doit être une chaîne.")

    selection_mode = raw_value.strip().lower() or "standard"

    if selection_mode not in SUPPORTED_SELECTION_MODES:
        allowed = ", ".join(sorted(SUPPORTED_SELECTION_MODES))
        raise AnalysisProfileError(f"Mode de sélection inconnu : {selection_mode!r}. Valeurs autorisées : {allowed}.")

    return selection_mode
