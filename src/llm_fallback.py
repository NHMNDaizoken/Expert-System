from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv

from src.config import ENV_PATH


load_dotenv(ENV_PATH)

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PLACEHOLDER_KEYS = {"", "your_gemini_api_key", "change_me", "changeme"}


def _has_api_key() -> bool:
    return bool(GEMINI_API_KEY and GEMINI_API_KEY.strip() not in PLACEHOLDER_KEYS)


def _prompt(user_input: str, top_k: int) -> str:
    return f"""
You are a cautious automotive diagnostic assistant used as a fallback when a
rule-based Knowledge Graph has no matching symptom.

Return only valid JSON. Do not include markdown.

User symptom text:
{user_input}

Create up to {top_k} possible diagnostic candidates. Prefer common automotive
faults. Keep confidence conservative because this is not from the approved KG.

JSON shape:
{{
  "diagnoses": [
    {{
      "fault_id": "LLM_SNAKE_CASE_ID",
      "fault_name": "snake_case_name",
      "fault_label": "Human readable fault",
      "system": "Vehicle system or Unknown",
      "final_cf": 0.0,
      "decision": "Needs expert review",
      "matched_rules": [
        {{
          "symptom_id": "USER_REPORTED_SYMPTOM",
          "symptom_name": "user_reported_symptom",
          "symptom_label": "short symptom label",
          "cf": 0.0,
          "priority": 1,
          "source": "llm_fallback"
        }}
      ],
      "repairs": [
        {{
          "repair_id": "LLM_CHECK_1",
          "repair_name": "initial_checks",
          "repair_label": "Initial checks",
          "steps": ["safe inspection step"]
        }}
      ]
    }}
  ],
  "notes": ["short caveat"]
}}
""".strip()


def _safe_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def _offline_response(user_input: str) -> dict[str, Any]:
    return {
        "diagnoses": [
            {
                "fault_id": "UNMAPPED_SYMPTOM",
                "fault_name": "unmapped_symptom",
                "fault_label": "Symptom is not covered by current KG",
                "system": "Unknown",
                "final_cf": 0.2,
                "decision": "Needs expert review",
                "matched_rules": [
                    {
                        "symptom_id": "USER_REPORTED_SYMPTOM",
                        "symptom_name": "user_reported_symptom",
                        "symptom_label": user_input,
                        "cf": 0.2,
                        "priority": 1,
                        "source": "offline_fallback",
                    }
                ],
                "repairs": [
                    {
                        "repair_id": "REP_COLLECT_MORE_DATA",
                        "repair_name": "collect_more_data",
                        "repair_label": "Collect more diagnostic data",
                        "steps": [
                            "Ask for vehicle system, warning lights, sound, smell, and when the symptom appears.",
                            "Add this symptom and confirmed expert rule to data/staging if it is a real case.",
                        ],
                    }
                ],
            }
        ],
        "notes": [
            "GEMINI_API_KEY is not configured, so no LLM diagnosis was generated.",
        ],
    }


def diagnose_with_llm(user_input: str, top_k: int = 5) -> dict[str, Any]:
    if not _has_api_key():
        return _offline_response(user_input)

    try:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(DEFAULT_MODEL)
        response = model.generate_content(_prompt(user_input, top_k))
        payload = _safe_json(response.text)
    except Exception as exc:
        payload = _offline_response(user_input)
        payload["notes"].append(f"LLM fallback failed: {exc}")

    diagnoses = payload.get("diagnoses", [])[:top_k]
    for index, diagnosis in enumerate(diagnoses, start=1):
        diagnosis.setdefault("fault_id", f"LLM_FAULT_{index}")
        diagnosis.setdefault("fault_name", diagnosis["fault_id"].lower())
        diagnosis.setdefault("fault_label", diagnosis["fault_name"])
        diagnosis.setdefault("system", "Unknown")
        diagnosis["final_cf"] = min(float(diagnosis.get("final_cf", 0.35)), 0.55)
        diagnosis.setdefault("decision", "Needs expert review")
        diagnosis.setdefault("matched_rules", [])
        diagnosis.setdefault("repairs", [])

    return {
        "diagnoses": diagnoses,
        "notes": payload.get("notes", []),
    }
