"""
run_auto_reconcile.
"""

from __future__ import annotations

from brainops.services.category_coherence_check import check_file_path_category_coherence
from brainops.services.reconcile_service import reconcile
from brainops.utils.logger import get_logger

logger = get_logger("Brainops Reconcile Scripts")


def run_reconcile_scripts() -> None:
    """
    Lance les scripts de reconciliation.
    """
    reconcile(scope="all", apply=True, logger=logger)
    # check_archives_syntheses_from_hash_source(auto_fix=True, logger=logger)
    check_file_path_category_coherence(auto_fix=True, sample_size=10, logger=logger)
