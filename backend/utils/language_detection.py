from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

# Script detection is a heuristic for WCAG 3.1.2.
# It is intentionally coarse-grained and designed to:
# - Detect likely foreign-language content
# - Avoid false positives on Latin text
# - Defer precise language identification to /Lang metadata

# BCP 47 language tag syntax
# Source:
#   RFC 5646 / RFC 4647 (BCP 47)
#   https://www.rfc-editor.org/rfc/rfc5646
LANG_TAG_PATTERN = re.compile(
    r"^[A-Za-z]{2,3}"
    r"(?:-(?:[A-Za-z]{4}|[A-Za-z]{2}|[0-9]{3}|[A-Za-z0-9]{5,8}))*$"
)

# Unicode script block detection
# Source:
#   Unicode Standard – Script & Block Code Charts
#   https://www.unicode.org/charts/
SCRIPT_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    # Cyrillic blocks (basic + extensions)
    ("Cyrillic", re.compile(r"[\u0400-\u052f\u2de0-\u2dff\ua640-\ua69f]")),

    # CJK: Hiragana, Katakana, CJK Unified Ideographs, Hangul
    ("CJK", re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")),

    # Arabic script (basic + extensions)
    ("Arabic", re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]")),

    # Hebrew script
    ("Hebrew", re.compile(r"[\u0590-\u05ff]")),

    # Greek script
    ("Greek", re.compile(r"[\u0370-\u03ff]")),

    # Indic scripts (Devanagari, Bengali, Gurmukhi, Gujarati,
    # Oriya, Tamil, Telugu, Kannada, Malayalam, Sinhala)
    # https://www.unicode.org/charts/PDF/U0900.pdf
    ("Indic", re.compile(r"[\u0900-\u0dff]")),
]

# Heuristic mapping from detected script → likely BCP 47 language subtags
#
# NOTE:
# These are hints only; scripts are shared across multiple languages.
SCRIPT_LANGUAGE_HINTS: Dict[str, Set[str]] = {
    "Cyrillic": {"ru", "uk", "bg", "sr", "mk", "be", "kk", "ky", "mn"},
    "Arabic": {"ar", "fa", "ur", "ps"},
    "CJK": {"zh", "ja", "ko"},
    "Hebrew": {"he", "iw", "yi"},
    "Greek": {"el"},

    # Indic languages (representative, not exhaustive)
    "Indic": {
        "hi",  # Hindi
        "mr",  # Marathi
        "ne",  # Nepali
        "bn",  # Bengali
        "pa",  # Punjabi
        "gu",  # Gujarati
        "or",  # Odia
        "ta",  # Tamil
        "te",  # Telugu
        "kn",  # Kannada
        "ml",  # Malayalam
        "si",  # Sinhala
    },
}


def normalize_lang_value(lang_value: Any) -> Optional[str]:
    """Return a clean string representation of a /Lang entry."""
    if lang_value is None:
        return None
    normalized = str(lang_value).strip()
    if normalized.startswith("/"):
        normalized = normalized[1:]
    return normalized or None


def is_valid_lang_tag(lang_value: Any) -> bool:
    """Validate BCP 47-style language tags using a compiled regex."""
    normalized = normalize_lang_value(lang_value)
    if not normalized:
        return False
    return bool(LANG_TAG_PATTERN.match(normalized))


def detect_script_hint(text: Optional[str]) -> Optional[str]:
    """Return a script label when non-Latin ranges appear in the text."""
    if not text:
        return None
    for label, pattern in SCRIPT_PATTERNS:
        if pattern.search(text):
            return label
    return None


def collect_script_hints(text: Optional[str]) -> Set[str]:
    """Return all script labels detected within the provided text snippet."""
    hints: Set[str] = set()
    if not text:
        return hints
    for label, pattern in SCRIPT_PATTERNS:
        if pattern.search(text):
            hints.add(label)
    return hints


def base_language(lang_value: Any) -> Optional[str]:
    """Return the primary language subtag for quick comparisons."""
    normalized = normalize_lang_value(lang_value)
    if not normalized:
        return None
    return normalized.lower().split("-")[0]


def lang_matches_script(lang_value: Any, script_hint: Optional[str]) -> bool:
    """Heuristically determine if a language tag already covers the script."""
    if not lang_value or not script_hint:
        return False
    base = base_language(lang_value)
    if not base:
        return False
    expected = SCRIPT_LANGUAGE_HINTS.get(script_hint)
    if not expected:
        return False
    return base in expected


__all__ = [
    "detect_script_hint",
    "collect_script_hints",
    "is_valid_lang_tag",
    "lang_matches_script",
    "normalize_lang_value",
]
