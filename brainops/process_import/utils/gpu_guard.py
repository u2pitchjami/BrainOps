from __future__ import annotations

import subprocess
import time
from typing import Final

from brainops.models.event import QueuedNoteContext
from brainops.ollama.check_ollama import check_ollama_health
from brainops.utils.logger import get_logger

LOGGER = get_logger("Brainops GPU Guard")

# ⚙️ Paramètres par défaut (configurables)
DEFAULT_MIN_VRAM_MB: Final[int] = 8192
DEFAULT_CHECK_INTERVAL_SEC: Final[int] = 180
DEFAULT_TIMEOUT_SEC: Final[int] = 3600
DEFAULT_MAX_RETRIES: Final[int] = 20


class GPUUnavailableError(RuntimeError):
    """
    Raised when GPU is not usable after timeout.
    """


def get_free_vram_mb() -> int:
    """
    Returns free GPU VRAM in MB using nvidia-smi.

    :raises RuntimeError: if nvidia-smi fails.
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        output = result.stdout.strip().splitlines()
        if not output:
            raise RuntimeError("No GPU detected")

        return int(output[0])

    except Exception as exc:  # pylint: disable=broad-except
        LOGGER.exception("Failed to query GPU VRAM")
        raise RuntimeError("Unable to query GPU VRAM") from exc


def guard_gpu_or_requeue(
    qnc: QueuedNoteContext,
    *,
    min_required_mb: int = DEFAULT_MIN_VRAM_MB,
    check_interval_sec: int = DEFAULT_CHECK_INTERVAL_SEC,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> bool:
    """
    Ensures sufficient VRAM before running an AI task.

    If VRAM is insufficient:
        - Waits up to timeout_sec
        - If still insufficient:
            - releases lock
            - requeues event
            - returns False

    Returns:
        True  -> continue processing
        False -> processing stopped (event requeued)
    """
    start_time = time.time()

    while True:
        free_vram = get_free_vram_mb()

        LOGGER.info(
            "[GPU GUARD] Free VRAM: %d MB (required: %d MB)",
            free_vram,
            min_required_mb,
        )

        if free_vram >= min_required_mb:
            if not check_ollama_health(logger=LOGGER):
                LOGGER.warning("[GPU GUARD] Ollama not ready despite sufficient VRAM.")
            else:
                LOGGER.info("[GPU GUARD] VRAM and Ollama ready.")
                return True

        elapsed = time.time() - start_time

        if elapsed >= timeout_sec:
            LOGGER.warning(
                "[GPU GUARD] Timeout reached (%.0f sec). Requeueing.",
                elapsed,
            )

            # --- Retry limit management ---
            retry_count = qnc.retry_count + 1
            qnc.retry_count = retry_count

            if retry_count > max_retries:
                LOGGER.error(
                    "[GPU GUARD] Max retries exceeded for note_id=%s",
                    qnc.note.id if qnc.note else None,
                )

                return False

            from brainops.watcher.queue_manager import replay_enqueue

            replay_enqueue(qnc)

            return False

        LOGGER.info(
            "[GPU GUARD] Insufficient VRAM. Retrying in %d sec...",
            check_interval_sec,
        )

        time.sleep(check_interval_sec)
