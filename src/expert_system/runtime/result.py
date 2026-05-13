"""
result — Typed data models for diagnosis response payloads.

Contains DiagnosisResponse and DiagnosisCandidate TypedDicts
used to structure the output of the expert-system engine.
"""
from __future__ import annotations

from typing import Any, TypedDict


class DiagnosisCandidate(TypedDict, total=False):
    fault_id: str
    fault_name: str
    fault_label: str
    system: str | None
    final_cf: float
    confidence: float
    confidence_label: str


class DiagnosisResponse(TypedDict, total=False):
    matched_symptoms: list[dict[str, Any]]
    diagnoses: list[dict[str, Any]]
    results: list[dict[str, Any]]
    current_hypotheses: list[dict[str, Any]]
    candidate_faults: list[DiagnosisCandidate]
    next_question: dict[str, Any] | None
    reasoning_trace: dict[str, Any]
    status: str
    is_final: bool
    tree_level: str
    explanation_summary: str
    source: str
    procedure_terminal: str | None
    resolution: dict[str, Any] | None
    confirmed_symptoms: list[str] | None
    rejected_symptoms: list[str] | None
    detected_systems: list[str] | None
    primary_symptom: str | None
    confirmed_context: list[str] | None
    rejected_context: list[str] | None
    active_fault_path: list[dict[str, Any]] | None
