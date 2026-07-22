from __future__ import annotations

import time
from typing import Any, Final

import requests

from brainops.models.event import QueuedNoteContext
from brainops.utils.config import OLLAMA_CPU_URL, OLLAMA_GPU_URL, PROMETHEUS_URL
from brainops.utils.logger import get_logger

LOGGER = get_logger("Brainops GPU Guard")

DEFAULT_MIN_VRAM_MB: Final[int] = 8192
DEFAULT_MAX_GPU_UTIL_PERCENT: Final[int] = 40
DEFAULT_MAX_GPU_TEMP_CELSIUS: Final[int] = 82
DEFAULT_CHECK_INTERVAL_SEC: Final[int] = 180
DEFAULT_TIMEOUT_SEC: Final[int] = 3600
DEFAULT_MAX_RETRIES: Final[int] = 20
DEFAULT_PROMETHEUS_TIMEOUT_SEC: Final[float] = 3.0
OLLAMA_PS_TIMEOUT_SEC = 3.0


class GPUUnavailableError(RuntimeError):
    """
    Raised when GPU is not usable after timeout.
    """


class PrometheusQueryError(RuntimeError):
    """
    Raised when Prometheus query fails.
    """


class OllamaStatusError(RuntimeError):
    """
    Raised when Ollama model status cannot be retrieved.
    """


def normalize_model_name(model_name: str) -> str:
    """
    Normalize an Ollama model name for comparison.
    """
    normalized = model_name.strip()

    if ":" not in normalized:
        return f"{normalized}:latest"

    return normalized


def get_gpu_loaded_models() -> set[str]:
    """
    Return model names currently loaded by the GPU Ollama instance.
    """
    try:
        response = requests.get(
            f"{OLLAMA_GPU_URL.rstrip('/')}/api/ps",
            timeout=OLLAMA_PS_TIMEOUT_SEC,
        )
        response.raise_for_status()

        payload: dict[str, Any] = response.json()
        raw_models = payload.get("models", [])

        if not isinstance(raw_models, list):
            raise OllamaStatusError("Invalid Ollama /api/ps response.")

        loaded_models: set[str] = set()

        for raw_model in raw_models:
            if not isinstance(raw_model, dict):
                continue

            raw_name = raw_model.get("name")

            if isinstance(raw_name, str):
                loaded_models.add(normalize_model_name(raw_name))

        return loaded_models

    except (requests.RequestException, ValueError) as exc:
        raise OllamaStatusError("Unable to retrieve loaded models from GPU Ollama.") from exc


def query_prometheus_value(
    query: str,
    *,
    prometheus_url: str = PROMETHEUS_URL,
    timeout_sec: float = DEFAULT_PROMETHEUS_TIMEOUT_SEC,
) -> float:
    """
    Query Prometheus instant API and return the first numeric value.

    Args:
        query: PromQL query.
        prometheus_url: Prometheus base URL.
        timeout_sec: HTTP timeout.

    Returns:
        First metric value as float.

    Raises:
        PrometheusQueryError: if Prometheus is unreachable or response is invalid.
    """
    try:
        response = requests.get(
            f"{prometheus_url.rstrip('/')}/api/v1/query",
            params={"query": query},
            timeout=timeout_sec,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()

        if payload.get("status") != "success":
            raise PrometheusQueryError(f"Prometheus query failed: {payload}")

        results = payload.get("data", {}).get("result", [])
        if not results:
            raise PrometheusQueryError(f"No Prometheus result for query: {query}")

        value = results[0].get("value")
        if not isinstance(value, list) or len(value) < 2:
            raise PrometheusQueryError(f"Invalid Prometheus value format: {value}")

        return float(value[1])

    except requests.RequestException as exc:
        LOGGER.exception("[GPU GUARD] Prometheus HTTP error")
        raise PrometheusQueryError("Unable to query Prometheus") from exc
    except (ValueError, TypeError, KeyError) as exc:
        LOGGER.exception("[GPU GUARD] Invalid Prometheus response")
        raise PrometheusQueryError("Invalid Prometheus response") from exc


def get_free_vram_mb() -> int:
    """
    Returns free GPU VRAM in MiB using Prometheus/DCGM.
    """
    return int(query_prometheus_value("DCGM_FI_DEV_FB_FREE"))


def get_used_vram_mb() -> int:
    """
    Returns used GPU VRAM in MiB using Prometheus/DCGM.
    """
    return int(query_prometheus_value("DCGM_FI_DEV_FB_USED"))


def get_gpu_util_percent() -> int:
    """
    Returns GPU utilization percentage using Prometheus/DCGM.
    """
    return int(query_prometheus_value("DCGM_FI_DEV_GPU_UTIL"))


def get_gpu_temperature_celsius() -> int:
    """
    Returns GPU temperature in Celsius using Prometheus/DCGM.
    """
    return int(query_prometheus_value("DCGM_FI_DEV_GPU_TEMP"))


def is_gpu_available(
    *,
    min_required_mb: int = DEFAULT_MIN_VRAM_MB,
    max_gpu_util_percent: int = DEFAULT_MAX_GPU_UTIL_PERCENT,
    max_gpu_temp_celsius: int = DEFAULT_MAX_GPU_TEMP_CELSIUS,
) -> bool:
    """
    Returns True if GPU seems available for BrainOps.

    If Prometheus is unavailable, returns False to allow CPU fallback.
    """
    try:
        free_vram = get_free_vram_mb()
        used_vram = get_used_vram_mb()
        gpu_util = get_gpu_util_percent()
        gpu_temp = get_gpu_temperature_celsius()

        LOGGER.info(
            "[GPU CHECK] free=%d MiB used=%d MiB util=%d%% temp=%d°C",
            free_vram,
            used_vram,
            gpu_util,
            gpu_temp,
        )

        return free_vram >= min_required_mb and gpu_util <= max_gpu_util_percent and gpu_temp <= max_gpu_temp_celsius

    except PrometheusQueryError:
        LOGGER.warning("[GPU CHECK] GPU metrics unavailable, fallback to CPU.")
        return False


def get_ollama_base_url(
    model_name: str,
    *,
    min_required_mb: int = DEFAULT_MIN_VRAM_MB,
) -> str:
    """
    Select the most appropriate Ollama backend.

    A model already loaded on the GPU remains eligible even if the remaining free VRAM is below the normal loading
    threshold.
    """
    normalized_model = normalize_model_name(model_name)

    try:
        loaded_models = get_gpu_loaded_models()
    except OllamaStatusError:
        LOGGER.warning("[OLLAMA ROUTING] Unable to inspect GPU Ollama models.")
    else:
        if normalized_model in loaded_models:
            LOGGER.info(
                "[OLLAMA ROUTING] backend=gpu model=%s reason=model_already_loaded",
                normalized_model,
            )
            return OLLAMA_GPU_URL

    if is_gpu_available(min_required_mb=min_required_mb):
        LOGGER.info(
            "[OLLAMA ROUTING] backend=gpu model=%s reason=enough_resources",
            normalized_model,
        )
        return OLLAMA_GPU_URL

    LOGGER.info(
        "[OLLAMA ROUTING] backend=cpu model=%s reason=gpu_resources_unavailable",
        normalized_model,
    )
    return OLLAMA_CPU_URL


def guard_gpu_or_requeue(
    qnc: QueuedNoteContext,
    *,
    min_required_mb: int = DEFAULT_MIN_VRAM_MB,
    check_interval_sec: int = DEFAULT_CHECK_INTERVAL_SEC,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> bool:
    """
    Ensures sufficient GPU capacity before running a GPU-only AI task.

    If GPU is unavailable:
        - waits up to timeout_sec
        - then requeues event
        - returns False

    Returns:
        True: continue processing
        False: processing stopped and possibly requeued
    """
    start_time = time.monotonic()

    while True:
        if is_gpu_available(min_required_mb=min_required_mb):
            from brainops.ollama.check_ollama import check_ollama_health

            if not check_ollama_health(logger=LOGGER):
                LOGGER.warning("[GPU GUARD] Ollama GPU not ready despite available GPU.")
            else:
                LOGGER.info("[GPU GUARD] GPU and Ollama ready.")
                return True

        elapsed = time.monotonic() - start_time

        if elapsed >= timeout_sec:
            LOGGER.warning(
                "[GPU GUARD] Timeout reached after %.0f sec. Requeueing.",
                elapsed,
            )

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
            "[GPU GUARD] GPU unavailable. Retrying in %d sec...",
            check_interval_sec,
        )
        time.sleep(check_interval_sec)
