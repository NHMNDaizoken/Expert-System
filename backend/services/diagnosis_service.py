from fastapi import HTTPException, status

from backend.services.session_service import SessionService
from src.expert_system.inference_engine import ExpertSystemEngine
from src.expert_system.knowledge_base import KnowledgeBase
from src.kg_inference import KGInference
from src.llm_fallback import diagnose_with_llm


def confidence_label(cf):
    if cf >= 0.8:
        return "Very likely"
    if cf >= 0.6:
        return "Likely"
    if cf >= 0.5:
        return "Possible"
    return "Uncertain"


def parse_answer(answer):
    normalized = answer.strip().lower()
    if normalized in {"yes", "y", "true", "1", "co", "có"}:
        return True
    if normalized in {"no", "n", "false", "0", "khong", "không"}:
        return False
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Answer must be yes or no.",
    )


def enrich_response(response):
    for result in response.get("results", []):
        cf = float(result.get("final_cf", 0))
        result["confidence_label"] = confidence_label(cf)
    return response


def estimate_step_progress(session, top_rule):
    history = session.get("step_history", []) if session else []
    if not history:
        return None
    total = len((top_rule or {}).get("procedure", {}).get("steps", {}))
    current = len(history)
    return f"{current}/{total}" if total > 0 else None


def should_use_llm_fallback(response):
    if response is None:
        return True
    candidates = response.get("diagnoses") or response.get("current_hypotheses") or []
    return response.get("status") in {"unknown_symptom", "no_fault_found"} or not candidates


def llm_response(user_input, top_k=5, reason="kg_no_match"):
    fallback = diagnose_with_llm(user_input, top_k=top_k)
    diagnoses = fallback.get("diagnoses", [])
    return {
        "matched_symptoms": [],
        "confirmed_symptoms": [],
        "rejected_symptoms": [],
        "detected_systems": [],
        "primary_symptom": None,
        "confirmed_context": [],
        "rejected_context": [],
        "active_fault_path": [],
        "tree_level": "symptom",
        "diagnoses": [],
        "results": [],
        "current_hypotheses": [],
        "fallback_suggestions": diagnoses,
        "next_question": None,
        "reasoning_trace": {
            "normalization": {
                "input": user_input,
                "status": "not_matched_by_kg",
                "source": "llm_fallback",
            },
            "hypothesis_generation": [
                {
                    "source": "llm_fallback",
                    "reason": reason,
                    "notes": fallback.get("notes", []),
                    "authority": "not_diagnostic",
                }
            ],
            "question_selection": {"status": "not_selected"},
            "backward_chaining": [],
            "cf_calculation_steps": [],
            "final_decision": {"status": "unknown_symptom", "top_fault": None},
            "ranking": [],
        },
        "explanation_summary": "Symptom was not mapped to the Knowledge Base; LLM fallback suggestions are non-authoritative.",
        "status": "unknown_symptom",
        "is_final": False,
        "source": "llm_fallback",
        "fallback_reason": reason,
        "fallback_notes": fallback.get("notes", []),
    }


class DiagnosisService:
    def __init__(self):
        self.sessions = SessionService()

    def diagnose(self, user_input=None, top_k=5, session_id=None, step_answer=None):
        if session_id:
            return self.continue_session(session_id, symptom=user_input, step_answer=step_answer, top_k=top_k)

        reason = "kg_no_match"
        try:
            response = enrich_response(ExpertSystemEngine.from_staging().diagnose(user_input, top_k=top_k))
            response["source"] = "staging_files_kg"
            response = self._force_interview_if_too_early(response, None)
        except Exception as exc:
            response = None
            reason = f"staging_kg_unavailable: {exc}"

        if should_use_llm_fallback(response):
            response = llm_response(user_input, top_k=top_k, reason=reason)

        response = self._add_response_context(response, None)
        session_id = self.sessions.create(user_input, response)
        response["session_id"] = session_id
        return response
    
    def _force_interview_if_too_early(self, response, session=None):
        """
        Safety guard: prevent one-shot diagnosis from a single primary symptom.
        The expert system should ask at least one follow-up question unless the
        engine explicitly marks the diagnosis as deterministic.
        """
        if not response:
            return response

        if response.get("status") != "diagnosed":
            return response

        if response.get("deterministic") is True:
            return response

        confirmed = response.get("confirmed_symptoms") or []
        hypotheses = response.get("results") or response.get("current_hypotheses") or []
        next_question = response.get("next_question")

        session_question_count = 0
        if session:
            session_question_count = len(session.get("step_history", []) or [])

        too_little_evidence = len(confirmed) <= 1 and session_question_count < 1

        if too_little_evidence:
            response["status"] = "need_more_info"
            response["is_final"] = False
            response["current_hypotheses"] = hypotheses
            response["results"] = []

            if not next_question:
                response["next_question"] = {
                    "question": "Cần thêm thông tin để xác nhận nguyên nhân. Triệu chứng này có xuất hiện liên tục không?",
                    "symptom": "symptom_persistent",
                    "symptom_id": "symptom_persistent",
                    "mode": "safety_follow_up",
                    "tree_level": "secondary_symptom",
                }

            response["explanation_summary"] = (
                "Initial symptom matched the knowledge base, but more evidence is required "
                "before producing a final diagnosis."
            )

        return response

    def _diagnose_with_available_engine(
        self,
        user_input,
        confirmed_symptoms,
        rejected_symptoms,
        session=None,
        top_k=5,
    ):
        response = enrich_response(
            ExpertSystemEngine.from_staging().diagnose(
                user_input,
                top_k=top_k,
                confirmed_symptoms=sorted(confirmed_symptoms),
                rejected_symptoms=sorted(rejected_symptoms),
                session=session,
            )
        )
        response["source"] = "staging_files_kg"
        return response

    def _rule_for_fault(self, fault_id):
        try:
            return KnowledgeBase.from_staging().get_fault(fault_id)
        except Exception:
            return None

    def _add_response_context(self, response, session):
        next_question = response.get("next_question") or {}
        hypotheses = response.get("current_hypotheses") or response.get("diagnoses") or []
        top = hypotheses[0] if hypotheses else None
        top_rule = self._rule_for_fault(top.get("fault_id")) if top else None
        progress = estimate_step_progress(session or {}, top_rule)

        mode = next_question.get("mode") or "information_gain"
        response.setdefault("mode", mode)
        response.setdefault("step_context", None)
        response.setdefault("step_progress", progress)
        response.setdefault("fault_preview", next_question.get("fault_preview"))
        response.setdefault("resolution", None)
        response["total_steps_est"] = len((top_rule or {}).get("procedure", {}).get("steps", {})) or None

        if progress:
            response["step_context"] = f"Diagnostic procedure · step {progress}"
        elif mode == "procedure_tree":
            response["step_context"] = "Diagnostic procedure"

        if response.get("status") == "diagnosed":
            response["results"] = response.get("results") or hypotheses
            if top_rule:
                response["resolution"] = top_rule.get("resolution")
        else:
            response.setdefault("results", [])
        return response

    def continue_session(self, session_id, symptom=None, step_answer=None, top_k=5):
        session = self.sessions.get(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Diagnosis session was not found.",
            )

        user_input = " ".join(part for part in [session.get("user_input", ""), symptom or ""] if part).strip()
        confirmed_symptoms = set(session.get("confirmed_symptoms", []))
        rejected_symptoms = set(session.get("rejected_symptoms", []))
        answers = dict(session.get("answers", {}))
        last_question = session.get("last_question") or {}

        if symptom:
            probe = KGInference.from_files()
            try:
                for match in probe.matcher.match(symptom):
                    confirmed_symptoms.add(match["symptom_id"])
            finally:
                probe.close()

        if step_answer is not None:
            if last_question.get("mode") == "information_gain" and last_question.get("symptom_id"):
                symptom_id = last_question["symptom_id"]
                answers[symptom_id] = bool(step_answer)
                if step_answer:
                    confirmed_symptoms.add(symptom_id)
                    rejected_symptoms.discard(symptom_id)
                else:
                    rejected_symptoms.add(symptom_id)
                    confirmed_symptoms.discard(symptom_id)
            self.sessions.update_step_state(session_id, last_question.get("step_id"), step_answer)
            session = self.sessions.get(session_id)

        response = self._diagnose_with_available_engine(
            user_input,
            confirmed_symptoms,
            rejected_symptoms,
            session=session,
            top_k=top_k,
        )
        response = self._force_interview_if_too_early(response, session)
        if should_use_llm_fallback(response):
            response = llm_response(user_input, reason="kg_no_match_after_answer")

        response = self._add_response_context(response, session)
        self.sessions.update_from_response(session_id, response, answers)
        if user_input and user_input != session.get("user_input"):
            # Preserve old schema while allowing the initial /session/new flow.
            pass
        response["session_id"] = session_id
        return response

    def answer(self, session_id, answer):
        session = self.sessions.get(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Diagnosis session was not found.",
            )

        last_question = session.get("last_question")
        if not last_question:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This session is not waiting for an answer.",
            )

        symptom = last_question["symptom"]
        answers = dict(session.get("answers", {}))
        answers[symptom] = parse_answer(answer)
        confirmed_symptoms = set(session.get("confirmed_symptoms", []))
        rejected_symptoms = set(session.get("rejected_symptoms", []))
        if answers[symptom]:
            confirmed_symptoms.add(symptom)
            rejected_symptoms.discard(symptom)
        else:
            rejected_symptoms.add(symptom)
            confirmed_symptoms.discard(symptom)

        response = self._diagnose_with_available_engine(
            session["user_input"],
            confirmed_symptoms,
            rejected_symptoms,
            session=session,
        )
        response = self._force_interview_if_too_early(response, session)

        if should_use_llm_fallback(response):
            response = llm_response(
                session["user_input"],
                reason="kg_no_match_after_answer",
            )

        response = self._add_response_context(response, session)
        self.sessions.update_from_response(session_id, response, answers)
        response["session_id"] = session_id
        return response
