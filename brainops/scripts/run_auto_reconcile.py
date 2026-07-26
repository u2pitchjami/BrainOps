"""
run_auto_reconcile.
"""

from __future__ import annotations

from brainops.services.reconcile_service import reconcile
from brainops.utils.logger import get_logger

logger = get_logger("Brainops Reconcile Scripts")


def run_reconcile_scripts() -> None:
    """
    Lance les scripts de reconciliation.
    """
    reconcile(scope="all", apply=True, logger=logger)
