"""
run_auto_reconcile.
"""

from __future__ import annotations

from brainops.services.check_emb_service import reconcile_embeddings
from brainops.services.emb_personal_service import personal_embeddings
from brainops.services.reconcile_service import reconcile
from brainops.services.reload_imports import scan_import_directory
from brainops.utils.logger import get_logger

logger = get_logger("Brainops Reconcile Scripts")


def run_reconcile_scripts() -> None:
    """
    Lance les scripts de reconciliation.
    """
    logger.info("Lancement des scripts de reconciliation...")
    reconcile(scope="all", apply=True, logger=logger)
    reconcile_embeddings(sample_size=5, logger=logger)
    personal_embeddings(logger=logger)
    scan_import_directory(logger=logger)
    logger.info("Scripts de reconciliation terminés.")
