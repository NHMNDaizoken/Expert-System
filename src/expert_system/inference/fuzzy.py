"""
fuzzy — Fuzzy symptom matching and normalization.

SymptomMatcher normalizes raw user text to Knowledge Base symptom IDs
using exact phrase matching and rapidfuzz token-set-ratio scoring.
"""
from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

MATCH_THRESHOLD = 88


class SymptomMatcher:
    """Normalize raw user text to Knowledge Base symptom IDs."""

    def __init__(self, symptom_aliases: dict[str, dict[str, Any]], threshold: int = MATCH_THRESHOLD):
        self.symptoms = symptom_aliases
        self.threshold = threshold
        self.candidates: list[tuple[str, str]] = []
        for symptom_id, symptom in symptom_aliases.items():
            terms = {
                symptom_id,
                symptom.get("name", ""),
                symptom.get("display_name", ""),
                symptom.get("label_vi", ""),
                *symptom.get("aliases", []),
            }
            for term in terms:
                if term:
                    self.candidates.append((symptom_id, term.lower()))

    def match(self, text: str) -> list[dict[str, Any]]:
        cleaned = (text or "").lower().strip()
        exact_by_symptom: dict[str, dict[str, Any]] = {}
        best_by_symptom: dict[str, dict[str, Any]] = {}

        for symptom_id, term in self.candidates:
            if self._is_exact_phrase_match(cleaned, term):
                symptom = self.symptoms[symptom_id]
                exact_by_symptom[symptom_id] = {
                    "symptom_id": symptom_id,
                    "name": symptom.get("name", symptom_id),
                    "display_name": symptom.get("display_name", symptom_id),
                    "matched_text": term,
                    "match_score": 100.0,
                    "confidence": 1.0,
                    "source": "symptom_aliases",
                }
                continue

            score = fuzz.token_set_ratio(cleaned, term)
            if score < self.threshold:
                continue
            current = best_by_symptom.get(symptom_id)
            if current is None or score > current["match_score"]:
                symptom = self.symptoms[symptom_id]
                best_by_symptom[symptom_id] = {
                    "symptom_id": symptom_id,
                    "name": symptom.get("name", symptom_id),
                    "display_name": symptom.get("display_name", symptom_id),
                    "matched_text": term,
                    "match_score": round(score, 2),
                    "confidence": round(score / 100, 4),
                    "source": "symptom_aliases",
                }

        matches = exact_by_symptom or best_by_symptom
        return sorted(matches.values(), key=lambda item: item["match_score"], reverse=True)

    @staticmethod
    def _is_exact_phrase_match(cleaned: str, term: str) -> bool:
        if not cleaned or not term:
            return False
        return cleaned == term or f" {term} " in f" {cleaned} "
