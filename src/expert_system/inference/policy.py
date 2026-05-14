"""
policy — Final decision and response policies.

apply_response_policy ensures that the response payload
has consistent status, results, and is_final flags based
on the diagnosis outcome and procedure terminal state.
"""
from __future__ import annotations

from typing import Any


def apply_response_policy(response: dict[str, Any]) -> dict[str, Any]:
    if response.get("status") == "llm_fallback":
        response["results"] = []
        response["is_final"] = False
        return response

    if response.get("status") == "suggested_diagnosis":
        response["is_final"] = False
        return response

    if response.get("status") != "diagnosed":
        response["results"] = []
        response["is_final"] = False
        return response

    # Engine đã diagnosed và không còn câu hỏi thì phải cho kết luận.
    if not response.get("next_question"):
        response["results"] = response.get("results") or response.get("current_hypotheses") or response.get("diagnoses") or []
        response["is_final"] = True
        return response

    if response.get("procedure_terminal") not in {None, "DIAGNOSED"}:
        response["status"] = "need_more_info"
        response["results"] = []
        response["is_final"] = False
        return response

    response["is_final"] = True
    return response
