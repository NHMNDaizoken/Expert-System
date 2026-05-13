from fastapi import HTTPException, status

from backend.services.diagnosis_normalizer import normalize_diagnosis_response
from backend.services.session_service import SessionService
from backend.core.dependencies import get_engine
from src.expert_system.inference.engine import ExpertSystemEngine
from src.expert_system.knowledge.loader import KnowledgeBase
from src.expert_system.inference.policy import apply_response_policy
from src.expert_system.llm_fallback import diagnose_with_llm
from src.expert_system.utils.scoring import confidence_label


MIN_CHAT_STEPS = 1



def parse_answer(answer):
    normalized = answer.strip().lower()
    if normalized in {"yes", "y", "true", "1", "co", "có"}:
        return True
    if normalized in {"no", "n", "false", "0", "khong", "không"}:
        return False
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Câu trả lời phải là có hoặc không.",
    )


def enrich_response(response):
    for result in response.get("results", []):
        cf = float(result.get("final_cf", 0))
        result["confidence_label"] = confidence_label(cf)
    return response


def question_key(question):
    if not question:
        return None
    return question.get("step_id") or question.get("symptom_id") or question.get("symptom") or question.get("mode")


def answered_step_count(session):
    if not session:
        return 0
    branch_path = session.get("branch_path", []) or []
    if branch_path:
        return len(branch_path)
    return len(session.get("step_history", []) or [])


def estimate_step_progress(session, response):
    current = answered_step_count(session)
    if response.get("status") == "need_more_info" and response.get("next_question"):
        current += 1
    return str(current) if current > 0 else None


def should_use_llm_fallback(response):
    if response is None:
        return True
    candidates = response.get("diagnoses") or response.get("current_hypotheses") or []
    return response.get("status") in {"unknown_symptom", "no_fault_found", "llm_fallback"} or not candidates


def filter_rejected_faults(response, rejected_faults):
    rejected_faults = set(rejected_faults or [])
    if not rejected_faults:
        return response

    for key in ["diagnoses", "results", "current_hypotheses", "candidate_faults"]:
        response[key] = [
            item for item in response.get(key, [])
            if item.get("fault_id") not in rejected_faults
        ]

    response["rejected_faults"] = sorted(rejected_faults)

    if not response.get("diagnoses") and not response.get("current_hypotheses"):
        response["status"] = "no_fault_found"
        response["is_final"] = False
        response["next_question"] = None
        response["results"] = []

    return response


def _extract_patch_next_question(patch):
    """Extract the first procedure tree entry-step question from an llm_kb_patch."""
    trees = patch.get("procedure_trees")
    faults = patch.get("candidate_faults")
    if not isinstance(trees, dict) or not trees:
        return None
    if not isinstance(faults, list) or not faults:
        return None

    # Pick the first candidate fault that has a matching procedure tree
    for fault in faults:
        if not isinstance(fault, dict):
            continue
        fault_id = fault.get("fault_id")
        tree = trees.get(fault_id)
        if not isinstance(tree, dict):
            continue
        entry = tree.get("entry_step")
        steps = tree.get("steps", {})
        step = steps.get(entry) if entry else None
        if step and step.get("question"):
            return {
                "question": step["question"],
                "answer_type": "yes_no",
                "source": "llm_fallback_procedure_tree",
                "fault_id": fault_id,
                "step_id": entry,
                "mode": "llm_fallback",
            }
    return None


def llm_response(user_input, top_k=5, reason="kg_no_match"):
    fallback = diagnose_with_llm(user_input, top_k=top_k)

    # Extract first question from the generated procedure tree
    patch_question = _extract_patch_next_question(fallback)

    # Fallback generic question when no procedure tree question available
    fallback_question = {
        "question": "Hệ thống chưa có đủ kiến thức đã kiểm duyệt cho triệu chứng này. Triệu chứng này thường xuất hiện khi nào?",
        "type": "multiple_choice",
        "mode": "llm_fallback",
        "choices": [
            {"value": "startup", "label": "Lúc khởi động"},
            {"value": "accelerating", "label": "Khi tăng tốc"},
            {"value": "idle", "label": "Khi chạy không tải"},
            {"value": "high_speed", "label": "Ở tốc độ cao"},
            {"value": "not_sure", "label": "Không chắc"},
        ],
        "why": [
            "Thông tin này giúp chuyên gia xác định hệ thống liên quan trước khi thêm luật mới vào Knowledge Graph."
        ],
    }

    response = {
        "matched_symptoms": [],
        "confirmed_symptoms": [],
        "rejected_symptoms": [],
        "rejected_faults": [],
        "detected_systems": [],
        "primary_symptom": None,
        "confirmed_context": [],
        "rejected_context": [],
        "active_fault_path": [],
        "tree_level": "symptom",

        # KHÔNG cho frontend render như kết quả thật
        "diagnoses": [],
        "results": [],
        "current_hypotheses": [],
        "candidate_faults": [],

        # LLM patch suggestion — for expert review only
        "llm_patch_suggestion": fallback,
        "queued_for_review": fallback.get("queued_for_review", False),
        "review_status": "pending",
        "review_type": "llm_kb_patch",

        # Use procedure tree question if available, else generic fallback
        "next_question": patch_question or fallback_question,

        "notes": ["Triệu chứng đã được đưa vào hàng chờ chuyên gia; chưa có kết luận cuối."],
        "reasoning_trace": [
            "Không tìm thấy triệu chứng phù hợp trong knowledge base.",
            "Đã đưa case vào hàng chờ chuyên gia.",
            "Cần hỏi thêm trước khi có thể chẩn đoán.",
        ],
        "explanation_summary": (
            "Triệu chứng chưa được ánh xạ vào cơ sở tri thức; "
            "cần thêm thông tin và chuyên gia duyệt."
        ),
        "status": "need_more_info",
        "is_final": False,
        "source": "llm_fallback",
        "fallback_reason": reason,
        "fallback_notes": [],
        "debug": {
            "fallback_reason": reason,
            "fallback_notes": fallback.get("review_notes", {}),
            "raw_fallback": fallback,
        },
    }
    response.update(normalize_diagnosis_response(response, raw_payload=fallback))
    return response


class DiagnosisService:
    def __init__(self):
        self.sessions = SessionService()

    def diagnose(
        self,
        user_input=None,
        top_k=5,
        session_id=None,
        step_answer=None,
        step_answer_provided=False,
    ):
        if session_id:
            return self.continue_session(
                session_id,
                symptom=user_input,
                step_answer=step_answer,
                step_answer_provided=step_answer_provided,
                top_k=top_k,
            )

        reason = "kg_no_match"
        try:
            response = get_engine().diagnose(user_input, top_k=top_k)
            response = apply_response_policy(response)
            response = enrich_response(response)
            response["source"] = "staging_files_kg"
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
        if response.get("status") != "diagnosed":
            return response

        if answered_step_count(session or {}) >= MIN_CHAT_STEPS:
            return response

        next_question = response.get("next_question")
        if next_question:
            response["status"] = "need_more_info"
            response["is_final"] = False
            response["results"] = []
            return response

        return response

    def _diagnose_with_available_engine(
        self,
        user_input,
        confirmed_symptoms,
        rejected_symptoms,
        rejected_faults=None,
        session=None,
        top_k=5,
    ):
        session_for_engine = dict(session or {})
        session_for_engine["rejected_faults"] = sorted(rejected_faults or [])

        response = enrich_response(
            get_engine().diagnose(
                user_input,
                top_k=top_k,
                confirmed_symptoms=sorted(confirmed_symptoms),
                rejected_symptoms=sorted(rejected_symptoms),
                session=session_for_engine,
            )
        )
        response["source"] = "staging_files_kg"
        response["rejected_faults"] = sorted(rejected_faults or [])
        return filter_rejected_faults(response, rejected_faults)

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
        progress = estimate_step_progress(session or {}, response)
        mode = next_question.get("mode") or "information_gain"

        response.setdefault("mode", mode)
        response.setdefault("step_context", None)
        response.setdefault("step_progress", progress)
        response.setdefault("fault_preview", next_question.get("fault_preview"))
        response.setdefault("resolution", None)
        response["total_steps_est"] = None

        if progress:
            response["step_context"] = f"Quy trình kiểm tra · bước {progress}"
        elif mode == "procedure_tree":
            response["step_context"] = "Quy trình kiểm tra"

        if response.get("status") == "diagnosed":
            response["results"] = response.get("results") or hypotheses
            if top_rule:
                response["resolution"] = top_rule.get("resolution")
        else:
            response.setdefault("results", [])

        response["normalized"] = normalize_diagnosis_response(response)
        return response

    def _reject_fault_from_last_question(self, last_question, rejected_faults):
        preview = last_question.get("fault_preview") or {}
        fault_id = preview.get("fault_id")
        if fault_id:
            rejected_faults.add(fault_id)

    def continue_session(
        self,
        session_id,
        symptom=None,
        step_answer=None,
        step_answer_provided=False,
        top_k=5,
    ):
        session = self.sessions.get(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy phiên chẩn đoán.",
            )

        user_input = " ".join(part for part in [session.get("user_input", ""), symptom or ""] if part).strip()
        confirmed_symptoms = set(session.get("confirmed_symptoms", []))
        rejected_symptoms = set(session.get("rejected_symptoms", []))
        rejected_faults = set(session.get("rejected_faults", []))
        answers = dict(session.get("answers", {}))
        last_question = session.get("last_question") or {}

        if symptom:
            engine = get_engine()
            try:
                for match in engine.matcher.match(symptom):
                    confirmed_symptoms.add(match["symptom_id"])
            except Exception:
                pass

        if step_answer_provided:
            symptom_id = last_question.get("symptom_id")
            if symptom_id and step_answer is not None:
                answers[symptom_id] = bool(step_answer)
                if step_answer:
                    confirmed_symptoms.add(symptom_id)
                    rejected_symptoms.discard(symptom_id)
                else:
                    rejected_symptoms.add(symptom_id)
                    confirmed_symptoms.discard(symptom_id)

            if step_answer is False:
                self._reject_fault_from_last_question(last_question, rejected_faults)

            self.sessions.update_step_state(session_id, question_key(last_question), step_answer)

        session = self.sessions.get(session_id) or session
        session["rejected_faults"] = sorted(rejected_faults)

        response = self._diagnose_with_available_engine(
            user_input,
            confirmed_symptoms,
            rejected_symptoms,
            rejected_faults=rejected_faults,
            session=session,
            top_k=top_k,
        )

        response = apply_response_policy(response)
        response = filter_rejected_faults(response, rejected_faults)

        if should_use_llm_fallback(response):
            response = llm_response(user_input, reason="kg_no_match_after_answer")
            response["rejected_faults"] = sorted(rejected_faults)

        response = self._add_response_context(response, session)
        response["rejected_faults"] = sorted(rejected_faults)

        self.sessions.update_from_response(session_id, response, answers, user_input=user_input)
        response["session_id"] = session_id
        return response

    def answer(self, session_id, answer):
        session = self.sessions.get(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy phiên chẩn đoán.",
            )

        last_question = session.get("last_question")
        if not last_question:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phiên này hiện không chờ câu trả lời.",
            )

        parsed_answer = parse_answer(answer)
        symptom = last_question.get("symptom_id") or last_question.get("symptom")
        answers = dict(session.get("answers", {}))

        if symptom:
            answers[symptom] = parsed_answer

        confirmed_symptoms = set(session.get("confirmed_symptoms", []))
        rejected_symptoms = set(session.get("rejected_symptoms", []))
        rejected_faults = set(session.get("rejected_faults", []))

        if symptom:
            if parsed_answer:
                confirmed_symptoms.add(symptom)
                rejected_symptoms.discard(symptom)
            else:
                rejected_symptoms.add(symptom)
                confirmed_symptoms.discard(symptom)

        if parsed_answer is False:
            self._reject_fault_from_last_question(last_question, rejected_faults)

        self.sessions.update_step_state(session_id, question_key(last_question), parsed_answer)

        session = self.sessions.get(session_id) or session
        session["rejected_faults"] = sorted(rejected_faults)

        response = self._diagnose_with_available_engine(
            session["user_input"],
            confirmed_symptoms,
            rejected_symptoms,
            rejected_faults=rejected_faults,
            session=session,
        )

        response = apply_response_policy(response)
        response = filter_rejected_faults(response, rejected_faults)

        if should_use_llm_fallback(response):
            response = llm_response(
                session["user_input"],
                reason="kg_no_match_after_answer",
            )
            response["rejected_faults"] = sorted(rejected_faults)

        response = self._add_response_context(response, session)
        response["rejected_faults"] = sorted(rejected_faults)

        self.sessions.update_from_response(session_id, response, answers, user_input=session["user_input"])
        response["session_id"] = session_id
        return response
