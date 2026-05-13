"""
text — Text normalization and slugification helpers.

Provides the slugify function used across the expert system
for generating consistent IDs from human-readable text.
"""
from __future__ import annotations

import re
from typing import Any


def slugify(text: Any) -> str:
    """Convert arbitrary text into a lowercase slug suitable for IDs."""
    text = str(text or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")
