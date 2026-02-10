"""
# process/split_windows_by_paragraphs.py
"""

from __future__ import annotations

import re

from brainops.process_import.split.split_utils import split_linear_text
from brainops.utils.logger import LoggerProtocol, ensure_logger


def split_windows_by_paragraphs(
    text: str, max_chars: int = 3800, overlap: int = 350, logger: LoggerProtocol | None = None
) -> list[str]:
    logger = ensure_logger(logger, __name__)
    paras = [p for p in re.split(r"\n{2,}", text) if p.strip()]
    windows: list[str] = []
    buf = ""

    for p in paras:
        if not buf:
            buf = p.strip()
            continue

        if len(buf) + 2 + len(p) <= max_chars:
            buf = f"{buf}\n\n{p.strip()}"
        else:
            windows.append(buf)
            buf = p.strip()

    if buf:
        windows.append(buf)

    # 🔴 FILET DE SÉCURITÉ FINAL
    safe: list[str] = []
    for w in windows:
        if len(w) <= max_chars:
            safe.append(w)
        else:
            logger.warning(
                "Paragraphe trop long, fallback linéaire (%d chars)",
                len(w),
            )
            safe.extend(
                split_linear_text(
                    w,
                    max_chars=max_chars,
                    overlap=overlap,
                )
            )

    return safe
