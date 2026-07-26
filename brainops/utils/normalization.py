"""
Utils normalization.
"""

# utils/normalization.py
from __future__ import annotations

from datetime import date, datetime
import re
import unicodedata

from brainops.io.paths import canonical_rel, to_abs
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.utils.logger import LoggerProtocol, ensure_logger


def normalize_full_path(path: str | bytes) -> str:
    """
    Normalise un chemin (NFC, strip, normalisation OS).
    """

    path = unicodedata.normalize("NFC", str(to_abs(str(path)))).strip()
    return canonical_rel(path)


def sanitize_created(created: object, *, logger: LoggerProtocol | None = None) -> str:
    """
    Normalise une date en 'YYYY-MM-DD'.

    Fallback = today().
    """
    logger = ensure_logger(logger, __name__)
    try:
        if isinstance(created, (datetime | date)):
            return created.strftime("%Y-%m-%d")
        if isinstance(created, str) and created.strip():
            try:
                parsed = datetime.fromisoformat(created.strip())
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                logger.warning("[sanitize_created] format invalide: %s", created)
                return datetime.now().strftime("%Y-%m-%d")
        return datetime.now().strftime("%Y-%m-%d")
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("[sanitize_created] erreur: %s", exc)
        return datetime.now().strftime("%Y-%m-%d")


def sanitize_yaml_title(title: str | None) -> str:
    """
    Nettoie un titre pour YAML (supprime chars problématiques, garde lettres/chiffres/espace/-/')
    """
    if not title:
        return "Untitled"
    try:
        title = unicodedata.normalize("NFC", title)
        title = re.sub(r"[^\w\s\-']", "", title)
        title = title.replace('"', "'").replace(":", " ")
        return title.strip() or "Untitled"
    except FileNotFoundError as exc:  # pylint: disable=broad-except
        raise BrainOpsError(
            "Note absente !!",
            code=ErrCode.NOFILE,
            ctx={"title": title},
        ) from exc
    except Exception as exc:  # pylint: disable=broad-except
        raise BrainOpsError(
            "Erreur inattendue exécutrice",
            code=ErrCode.UNEXPECTED,
            ctx={"title": title},
        ) from exc


def sanitize_filename(filename: str, *, logger: LoggerProtocol | None = None) -> str:
    """
    Nettoie un nom de fichier (compatible Windows/Unix).
    """
    logger = ensure_logger(logger, __name__)
    try:
        sanitized = re.sub(r'[<>:"/\\|?*]', " ", filename)
        # sanitized = sanitized.replace(" ", "_")
        return sanitized
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("[sanitize_filename] erreur: %s", exc)
        return "file"


def is_probably_code(block: str) -> bool:
    """
    Heuristique bloc code (grossière mais utile).
    """
    if re.search(r"[=;{}()<>]|(def |class |import |from )|#!/bin/", block):
        return True
    lines = block.splitlines()
    return len(lines) >= 3 and all(len(line) > 20 for line in lines)


def is_probably_inline_code(text: str) -> bool:
    """
    Heuristique inline code.
    """
    keywords = [
        "=",
        ";",
        "{",
        "}",
        "(",
        ")",
        "<",
        ">",
        "def",
        "class",
        "import",
        "from",
        "lambda",
    ]
    return any(k in text for k in keywords)


def clean_inline_code(text: str) -> str:
    """
    Supprime les `inline` s'ils ne ressemblent pas à du code.
    """
    return re.sub(
        r"`([^`\n]+?)`",
        lambda m: m.group(1) if not is_probably_inline_code(m.group(1)) else m.group(0),
        text,
    )


def clean_indented_code_lines(text: str) -> str:
    """
    Désindente les fausses lignes de code (indentées mais non-code, hors ```).
    """
    lines = text.splitlines()
    cleaned: list[str] = []
    in_code = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            cleaned.append(line)
            continue

        if not in_code:
            prev = lines[i - 1] if i > 0 else ""
            is_indented = line.startswith("    ") or line.startswith("\t")
            if is_indented and not prev.strip() and not is_probably_code(line):
                cleaned.append(line.lstrip())
                continue

        cleaned.append(line)

    return "\n".join(cleaned)


def clean_fake_code_blocks(text: str) -> str:
    """
    Nettoie les blocs ```...``` non-code + les `inline` non-code + indentations douteuses.
    """
    parts = re.split(r"(```(?:\w+)?\n.*?\n```)", text, flags=re.DOTALL)
    result: list[str] = []

    for part in parts:
        if part.startswith("```"):
            lines = part.splitlines()
            code_block = "\n".join(lines[1:-1])  # sans les ```
            if is_probably_code(code_block):
                result.append(part)
            else:
                cleaned = "\n".join(line.lstrip() for line in code_block.splitlines())
                result.append(cleaned)
        else:
            result.append(part)

    out = "\n".join(result)
    out = clean_inline_code(out)
    out = clean_indented_code_lines(out)
    return out
