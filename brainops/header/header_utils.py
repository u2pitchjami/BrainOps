"""
header.header_utils.
"""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import re
from typing import Any

import yaml

from brainops.models.types import _YAML_FENCE
from brainops.utils.logger import LoggerProtocol, ensure_logger


def get_yaml(content: str, *, logger: LoggerProtocol | None = None) -> dict[str, Any]:
    logger = ensure_logger(logger, __name__)
    try:
        m = _YAML_FENCE.match(content)
        if m:
            loaded = yaml.safe_load(m.group(1)) or {}
            if isinstance(loaded, dict):
                return loaded
            logger.warning("[get_yaml] YAML n'est pas un dict (%s), fallback {}", type(loaded).__name__)
            return {}
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(f"[get_yaml] Erreur parsing YAML : {exc}")
    return {}


def get_yaml_value(
    content: str, key: str, default: str | None = None, *, logger: LoggerProtocol | None = None
) -> Any | None:
    """
    get_yaml_value _summary_

    _extended_summary_

    Args:
        content (str): _description_
        key (str): _description_
        default (_type_, optional): _description_. Defaults to None.
        logger (LoggerProtocol | None, optional): _description_. Defaults to None.

    Returns:
        _type_: _description_
    """
    logger = ensure_logger(logger, __name__)
    y = get_yaml(content, logger=logger)
    if y is None:
        return None
    return y.get(key, default)


def update_yaml_header(content: str, new_metadata: dict[str, str], *, logger: LoggerProtocol | None = None) -> str:
    """
    Remplace l’en-tête YAML par new_metadata (écrase tout l’entête).
    """
    _ = ensure_logger(logger, __name__)
    new_yaml = yaml.safe_dump(new_metadata, default_flow_style=False, sort_keys=False, allow_unicode=True)
    new_front = f"---\n{new_yaml}---\n"

    m = _YAML_FENCE.match(content)
    body = content[len(m.group(0)) :] if m else content
    return new_front + body


def merge_yaml_header(
    content: str, new_metadata: dict[str, str | int | list[str]], *, logger: LoggerProtocol | None = None
) -> str:
    """
    Fusionne de nouvelles métadonnées dans l’en-tête YAML (conserve le reste).
    """
    logger = ensure_logger(logger, __name__)
    try:
        m = _YAML_FENCE.match(content)
        if m:
            existing = yaml.safe_load(m.group(1)) or {}
            body = content[len(m.group(0)) :]
        else:
            existing = {}
            body = content

        merged = {**existing, **new_metadata}
        new_yaml = yaml.safe_dump(merged, default_flow_style=False, sort_keys=False, allow_unicode=True)
        return f"---\n{new_yaml}---\n{body}"
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("[ERROR] merge_yaml_header: %s", exc)
        return content


def patch_yaml_line(
    yaml_text: str,
    key: str,
    patch_func: Callable[[str], str],
    *,
    logger: LoggerProtocol | None = None,
) -> str:
    """
    Applique une fonction de transformation sur la valeur d'une ligne 'key: value' (yaml_text = bloc YAML +
    délimiteurs).
    """
    _ = ensure_logger(logger, __name__)
    pattern = rf"^({re.escape(key)}\s*:\s*)(.+)$"
    return re.sub(
        pattern,
        lambda m: f"{m.group(1)}{patch_func(m.group(2))}",
        yaml_text,
        flags=re.MULTILINE,
    )


def hash_source(source: str) -> str:
    """
    hash_source _summary_

    _extended_summary_

    Args:
        source (str): _description_

    Returns:
        str: _description_
    """
    return hashlib.sha256(source.strip().lower().encode("utf-8")).hexdigest()
