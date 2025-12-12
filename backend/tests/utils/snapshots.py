"""
Helpers for loading pre-generated JSON snapshots in tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

EXPECTED_DIR = Path(__file__).parents[1] / "fixtures" / "expected"


def snapshot_json(expected_name: str) -> Dict[str, Any]:
    """
    Load a pre-generated expected JSON snapshot from the fixtures/expected directory.
    """
    path = EXPECTED_DIR / expected_name
    return json.loads(path.read_text(encoding="utf-8"))
