from __future__ import annotations

from pathlib import Path

from brainops.analysis.config import AnalysisConfig
from brainops.analysis.loader import (
    AnalysisProfileError,
    load_analysis_profile,
)
from brainops.utils.logger import LoggerProtocol, ensure_logger


def build_analysis_config(
    profile_name: str | None,
    *,
    profiles_dir: Path,
    logger: LoggerProtocol | None = None,
) -> AnalysisConfig:
    """
    Construit une configuration d'analyse depuis un profil YAML.

    Un profil absent provoque un fallback vers `generic`.
    Un profil existant mais invalide provoque une erreur.
    """
    logger = ensure_logger(logger, __name__)

    requested_profile = profile_name.strip().lower() if profile_name and profile_name.strip() else "generic"

    try:
        config = load_analysis_profile(
            requested_profile,
            profiles_dir=profiles_dir,
        )

    except FileNotFoundError as exc:
        if requested_profile == "generic":
            raise AnalysisProfileError("Le profil obligatoire 'generic' est introuvable.") from exc

        logger.warning(
            "[ANALYSIS] Profil '%s' introuvable, fallback vers 'generic'.",
            requested_profile,
        )

        config = load_analysis_profile(
            "generic",
            profiles_dir=profiles_dir,
        )

    logger.info(
        "[ANALYSIS] Profil chargé : %s",
        config.profile,
        extra={
            "instruction_count": len(config.instructions),
            "reflection_question_count": len(config.reflection_questions),
        },
    )

    return config
