from __future__ import annotations

from typing import Any


def apply_response_policy(response: dict[str, Any]) -> dict[str, Any]:
    if response.get("status") != "diagnosed":
        response["results"] = []
        response["is_final"] = False
        return response

    if response.get("procedure_terminal") != "DIAGNOSED":
        response["status"] = "need_more_info"
        response["results"] = []
        response["is_final"] = False
        return response

    response["is_final"] = True
    return response
