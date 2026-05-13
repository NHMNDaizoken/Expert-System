"""
scoring — Certainty-factor arithmetic and confidence label helpers.

Contains the MYCIN-style CF combination formula and the
Vietnamese confidence-level label mapper.
"""
from __future__ import annotations


def combine_cf(cf_old: float, cf_new: float) -> float:
    """MYCIN-style incremental certainty factor combination."""
    return cf_old + cf_new * (1 - cf_old)


def confidence_label(score: float) -> str:
    """Map a numeric CF score to a Vietnamese confidence label."""
    if score >= 0.8:
        return "Rất có khả năng"
    if score >= 0.6:
        return "Có khả năng"
    if score >= 0.4:
        return "Có thể xảy ra"
    return "Chưa chắc chắn"
