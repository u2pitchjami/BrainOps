"""2025-09-04 - module config en lien avec env."""

# config.py
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Chargement du .env
load_dotenv("/app/config/.env")


class ConfigError(Exception):
    """
    Erreur de configuration (.env / variables d'environnement).
    """


# --- Fonctions utilitaires ---


def get_required(key: str) -> str:
    """
    Récupère la valeur d'une variable env requise.

    Lève ConfigError si absente.
    """
    value = os.getenv(key)
    if value is None:
        raise ConfigError(f"[CONFIG ERROR] La variable {key} est requise mais absente.")
    return value


def get_bool(key: str, default: str = "false") -> bool:
    """
    Retourne la variable env convertie en booléen.
    """
    return os.getenv(key, default).lower() in ("true", "1", "yes", "y")


def get_str(key: str, default: str = "") -> str:
    """
    Retourne la variable env sous forme de chaîne.
    """
    return os.getenv(key, default)


def get_int(key: str, default: int = 0) -> int:
    """
    Retourne la variable env convertie en entier.

    Lève ConfigError si conversion impossible.
    """
    raw = os.getenv(key, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"[CONFIG ERROR] La variable {key} doit être un entier (valeur: {raw!r}).") from exc


def get_float(key: str, default: float = 0.0) -> float:
    """
    Retourne la variable env convertie en float.

    Lève ConfigError si conversion impossible.
    """
    raw = os.getenv(key, str(default))
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"[CONFIG ERROR] La variable {key} doit être un float (valeur: {raw!r}).") from exc


def get_path_required(key: str) -> str:
    """
    Retourne un chemin (str) *existant* lu depuis l'env.

    Lève ConfigError si absent ou inexistant.
    """
    from brainops.io.paths import to_abs

    value = get_required(key).strip()
    abs_path = str(value)
    if not Path(to_abs(abs_path)).exists():
        raise ConfigError(f"[CONFIG ERROR] {key} pointe vers un chemin inexistant: {abs_path}")
    return abs_path


# --- Variables d'environnement accessibles globalement ---

# LOGS
LOG_FILE_PATH: str = get_str("LOG_FILE_PATH", "/logs")
LOG_ROTATION_DAYS: int = get_int("LOG_ROTATION_DAYS", 30)
LOG_LEVEL: str = get_str("LOG_LEVEL", "INFO").upper()

# PATHS
BASE_PATH: str = get_required("BASE_PATH")
Z_STORAGE_PATH: str = get_path_required("Z_STORAGE_PATH")
SAV_PATH: str = get_path_required("SAV_PATH")
SIMILARITY_WARNINGS_LOG: str = get_str("SIMILARITY_WARNINGS_LOG", "/logs/similarity_warnings.log")
UNCATEGORIZED_JSON: str = get_str("UNCATEGORIZED_JSON", "/logs/uncategorized_notes.json")
UNCATEGORIZED_PATH: str = get_path_required("UNCATEGORIZED_PATH")
DUPLICATES_LOGS: str = get_str("DUPLICATES_LOGS", "/logs/duplicates_log.txt")
DUPLICATES_PATH: str = get_path_required("DUPLICATES_PATH")
IMPORTS_PATH: str = get_path_required("IMPORTS_PATH")
ERRORED_PATH: str = get_path_required("ERRORED_PATH")
ERRORED_JSON: str = get_str("ERRORED_JSON")
MANIFEST_DIR = str(get_path_required("MANIFEST_DIR"))
WORK_DIR = str(get_path_required("WORK_DIR"))

MAINTENANCE_TIMING: int = get_int("MAINTENANCE_TIMING", 3600)
LOCK_PURGE: int = get_int("LOCK_PURGE", 7200)

WATCHDOG_POLL_INTERVAL: float = get_float("WATCHDOG_POLL_INTERVAL", 1.0)
WATCHDOG_DEBOUNCE_WINDOW: float = get_float("WATCHDOG_DEBOUNCE_WINDOW", 0.5)

# OLLAMA
OLLAMA_URL_GENERATE = get_required("OLLAMA_URL_GENERATE")
OLLAMA_URL_EMBEDDINGS = get_required("OLLAMA_URL_EMBEDDINGS")
OLLAMA_TIMEOUT = get_int("OLLAMA_TIMEOUT", 100)
MODEL_LARGE_NOTE: str = get_str("MODEL_LARGE_NOTE", "mistral:latest")
MODEL_FR: str = get_str("MODEL_FR", "llama3.1:8b-instruct-q8_0")
MODEL_EN: str = get_str("MODEL_EN", "llama3.1:8b-instruct-q8_0")
MODEL_GET_TYPE: str = get_str("MODEL_GET_TYPE", "mistral:latest")
MODEL_EMBEDDINGS: str = get_str("MODEL_EMBEDDINGS", "nomic-embed-text:latest")
MODEL_SUMMARY: str = get_str("MODEL_SUMMARY", "cognitivetech/obook_summary:latest")

# DB
DB_HOST = str(get_required("DB_HOST"))
DB_PORT = int(get_int("DB_PORT"))
DB_USER = str(get_required("DB_USER"))
DB_PASSWORD = str(get_required("DB_PASSWORD"))
DB_NAME = str(get_required("DB_NAME"))
