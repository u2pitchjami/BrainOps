# brainops/config/check_config.py

from pathlib import Path

from brainops.models.reconcile import CheckConfig
from brainops.utils.config import BASE_NOTES, BASE_PATH, LOG_FILE_PATH


def get_check_config(scope: str = "all") -> CheckConfig:
    base = Path(BASE_PATH)
    base_notes = Path(BASE_NOTES)
    out = Path(LOG_FILE_PATH)

    return CheckConfig(base_path=base, base_notes=base_notes, out_dir=out)
